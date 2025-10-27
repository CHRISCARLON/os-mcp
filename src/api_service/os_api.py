import os
import aiohttp
import asyncio
import re
import concurrent.futures
import threading

from typing import Dict, List, Any, Optional
from models import (
    NGDAPIEndpoint,
    OpenAPISpecification,
    Collection,
    CollectionsCache,
    CollectionQueryables,
)
from api_service.protocols import APIClient
from utils.logging_config import get_logger

logger = get_logger(__name__)


class OSAPIClient(APIClient):
    """Implementation an OS API client"""

    user_agent = "os-ngd-mcp-server/1.0"

    def __init__(self, api_key: Optional[str] = None, max_concurrent_requests: int = 5):
        """
        Initialise the OS API client

        Args:
            api_key: Optional API key, if not provided will use OS_API_KEY env var
            max_concurrent_requests: Maximum number of concurrent requests (default: 5)
        """
        self.api_key = api_key
        self.session = None
        self.last_request_time = 0

        # Configurable rate limiting - reduced from 0.7s to 0.3s for better performance
        # Can be adjusted based on API quota
        self.request_delay = float(os.environ.get("OS_API_RATE_LIMIT", "0.3"))
        self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._cached_openapi_spec: Optional[OpenAPISpecification] = None
        self._cached_collections: Optional[CollectionsCache] = None

    # Private helper methods
    def _sanitise_api_key(self, text: Any) -> str:
        """Remove API keys from any text (URLs, error messages, etc.)"""
        if not isinstance(text, str):
            return text

        patterns = [
            r"[?&]key=[^&\s]*",
            r"[?&]api_key=[^&\s]*",
            r"[?&]apikey=[^&\s]*",
            r"[?&]token=[^&\s]*",
        ]

        sanitized = text
        for pattern in patterns:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

        sanitized = re.sub(r"[?&]$", "", sanitized)
        sanitized = re.sub(r"&{2,}", "&", sanitized)
        sanitized = re.sub(r"\?&", "?", sanitized)

        return sanitized

    def _sanitise_response(self, data: Any) -> Any:
        """Remove API keys from response data recursively"""
        if isinstance(data, dict):
            sanitized_dict = {}
            for key, value in data.items():
                if isinstance(value, str) and any(
                    url_indicator in key.lower()
                    for url_indicator in ["href", "url", "link", "uri"]
                ):
                    sanitized_dict[key] = self._sanitise_api_key(value)
                elif isinstance(value, (dict, list)):
                    sanitized_dict[key] = self._sanitise_response(value)
                else:
                    sanitized_dict[key] = value
            return sanitized_dict
        elif isinstance(data, list):
            return [self._sanitise_response(item) for item in data]
        elif isinstance(data, str):
            if any(
                indicator in data
                for indicator in [
                    "http://",
                    "https://",
                    "key=",
                    "api_key=",
                    "apikey=",
                    "token=",
                ]
            ):
                return self._sanitise_api_key(data)

        return data

    def _filter_latest_collections(
        self, collections: List[Dict[str, Any]]
    ) -> List[Collection]:
        """
        Filter collections to keep only the latest version of each collection type.
        For collections with IDs like 'trn-ntwk-roadlink-1', 'trn-ntwk-roadlink-2', 'trn-ntwk-roadlink-3',
        only keep the one with the highest number.

        Args:
            collections: Raw collections from API

        Returns:
            Filtered list of Collection objects
        """
        latest_versions: Dict[str, Dict[str, Any]] = {}

        for col in collections:
            col_id = col.get("id", "")

            match = re.match(r"^(.+?)-(\d+)$", col_id)

            if match:
                base_name = match.group(1)
                version_num = int(match.group(2))

                if (
                    base_name not in latest_versions
                    or version_num > latest_versions[base_name]["version"]
                ):
                    latest_versions[base_name] = {"version": version_num, "data": col}
            else:
                latest_versions[col_id] = {"version": 0, "data": col}

        filtered_collections = []
        for item in latest_versions.values():
            col_data = item["data"]
            filtered_collections.append(
                Collection(
                    id=col_data.get("id", ""),
                    title=col_data.get("title", ""),
                    description=col_data.get("description", ""),
                    links=col_data.get("links", []),
                    extent=col_data.get("extent", {}),
                    itemType=col_data.get("itemType", "feature"),
                )
            )

        return filtered_collections

    def _parse_openapi_spec_for_llm(
        self, spec_data: dict, collection_ids: List[str]
    ) -> dict:
        """Parse OpenAPI spec to extract only essential information for LLM context"""
        supported_crs = {
            "input": [],
            "output": [],
            "default": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        }

        parsed = {
            "title": spec_data.get("info", {}).get("title", ""),
            "version": spec_data.get("info", {}).get("version", ""),
            "base_url": spec_data.get("servers", [{}])[0].get("url", ""),
            "endpoints": {},
            "collection_ids": collection_ids,
            "supported_crs": supported_crs,
        }

        paths = spec_data.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method == "get" and "parameters" in details:
                    for param in details["parameters"]:
                        param_name = param.get("name", "")

                        if param_name == "collectionId" and "schema" in param:
                            enum_values = param["schema"].get("enum", [])
                            if enum_values:
                                parsed["collection_ids"] = enum_values

                        elif (
                            param_name in ["bbox-crs", "filter-crs"]
                            and "schema" in param
                        ):
                            crs_values = param["schema"].get("enum", [])
                            if crs_values and not supported_crs["input"]:
                                supported_crs["input"] = crs_values

                        elif param_name == "crs" and "schema" in param:
                            crs_values = param["schema"].get("enum", [])
                            if crs_values and not supported_crs["output"]:
                                supported_crs["output"] = crs_values

        endpoint_patterns = {
            "/collections": "List all collections",
            "/collections/{collectionId}": "Get collection info",
            "/collections/{collectionId}/schema": "Get collection schema",
            "/collections/{collectionId}/queryables": "Get collection queryables",
            "/collections/{collectionId}/items": "Search features in collection",
            "/collections/{collectionId}/items/{featureId}": "Get specific feature",
        }
        parsed["endpoints"] = endpoint_patterns
        parsed["crs_guide"] = {
            "WGS84": "http://www.opengis.net/def/crs/OGC/1.3/CRS84 (default, longitude/latitude)",
            "British_National_Grid": "http://www.opengis.net/def/crs/EPSG/0/27700 (UK Ordnance Survey)",
            "WGS84_latlon": "http://www.opengis.net/def/crs/EPSG/0/4326 (latitude/longitude)",
            "Web_Mercator": "http://www.opengis.net/def/crs/EPSG/0/3857 (Web mapping)",
        }

        return parsed

    # Private async methods
    async def _get_open_api_spec(self) -> OpenAPISpecification:
        """Get the OpenAPI spec for the OS NGD API"""
        try:
            response = await self.make_request("OPENAPI_SPEC", params={"f": "json"})

            # Sanitize the raw response before processing
            sanitized_response = self._sanitise_response(response)

            collections_cache = await self.cache_collections()
            filtered_collection_ids = [col.id for col in collections_cache.collections]

            parsed_spec = self._parse_openapi_spec_for_llm(
                sanitized_response, filtered_collection_ids
            )

            spec = OpenAPISpecification(
                title=parsed_spec["title"],
                version=parsed_spec["version"],
                base_url=parsed_spec["base_url"],
                endpoints=parsed_spec["endpoints"],
                collection_ids=filtered_collection_ids,
                supported_crs=parsed_spec["supported_crs"],
                crs_guide=parsed_spec["crs_guide"],
            )
            return spec
        except Exception as e:
            raise ValueError(f"Failed to get OpenAPI spec: {e}")

    async def cache_openapi_spec(self) -> OpenAPISpecification:
        """
        Cache the OpenAPI spec.

        Returns:
            The cached OpenAPI spec
        """
        if self._cached_openapi_spec is None:
            logger.debug("Caching OpenAPI spec for LLM context...")
            try:
                self._cached_openapi_spec = await self._get_open_api_spec()
                logger.debug("OpenAPI spec successfully cached")
            except Exception as e:
                raise ValueError(f"Failed to cache OpenAPI spec: {e}")
        return self._cached_openapi_spec

    async def _get_collections(self) -> CollectionsCache:
        """Get all collections from the OS NGD API"""
        try:
            response = await self.make_request("COLLECTIONS")
            collections_list = response.get("collections", [])
            filtered = self._filter_latest_collections(collections_list)
            logger.debug(f"Filtered collections: {len(filtered)} collections")
            return CollectionsCache(collections=filtered, raw_response=response)
        except Exception as e:
            sanitized_error = self._sanitise_api_key(str(e))
            logger.error(f"Error getting collections: {sanitized_error}")
            raise ValueError(f"Failed to get collections: {sanitized_error}")

    async def cache_collections(self) -> CollectionsCache:
        """
        Cache the collections data with filtering applied.

        Returns:
            The cached collections
        """
        if self._cached_collections is None:
            logger.debug("Caching collections for LLM context...")
            try:
                self._cached_collections = await self._get_collections()
                logger.debug(
                    f"Collections successfully cached - {len(self._cached_collections.collections)} collections after filtering"
                )
            except Exception as e:
                sanitized_error = self._sanitise_api_key(str(e))
                raise ValueError(f"Failed to cache collections: {sanitized_error}")
        return self._cached_collections

    async def fetch_collections_queryables(
        self, collection_ids: List[str]
    ) -> Dict[str, CollectionQueryables]:
        """Fetch detailed queryables for specific collections only"""
        if not collection_ids:
            return {}

        logger.debug(f"Fetching queryables for specific collections: {collection_ids}")

        collections_cache = await self.cache_collections()
        collections_map = {coll.id: coll for coll in collections_cache.collections}

        tasks = [
            self.make_request("COLLECTION_QUERYABLES", path_params=[collection_id])
            for collection_id in collection_ids
            if collection_id in collections_map
        ]

        if not tasks:
            return {}

        raw_queryables = await asyncio.gather(*tasks, return_exceptions=True)

        def process_single_collection_queryables(collection_id, queryables_data):
            collection = collections_map[collection_id]
            logger.debug(
                f"Processing collection {collection.id} in thread {threading.current_thread().name}"
            )

            if isinstance(queryables_data, Exception):
                logger.warning(
                    f"Failed to fetch queryables for {collection.id}: {queryables_data}"
                )
                return (
                    collection.id,
                    CollectionQueryables(
                        id=collection.id,
                        title=collection.title,
                        description=collection.description,
                        all_queryables={},
                        enum_queryables={},
                        has_enum_filters=False,
                        total_queryables=0,
                        enum_count=0,
                    ),
                )

            all_queryables = {}
            enum_queryables = {}
            properties = queryables_data.get("properties", {})

            for prop_name, prop_details in properties.items():
                prop_type = prop_details.get("type", ["string"])
                if isinstance(prop_type, list):
                    main_type = prop_type[0] if prop_type else "string"
                    is_nullable = "null" in prop_type
                else:
                    main_type = prop_type
                    is_nullable = False

                all_queryables[prop_name] = {
                    "type": main_type,
                    "nullable": is_nullable,
                    "max_length": prop_details.get("maxLength"),
                    "format": prop_details.get("format"),
                    "pattern": prop_details.get("pattern"),
                    "minimum": prop_details.get("minimum"),
                    "maximum": prop_details.get("maximum"),
                    "is_enum": prop_details.get("enumeration", False),
                }

                if prop_details.get("enumeration") and "enum" in prop_details:
                    enum_queryables[prop_name] = {
                        "values": prop_details["enum"],
                        "type": main_type,
                        "nullable": is_nullable,
                        "max_length": prop_details.get("maxLength"),
                    }
                    all_queryables[prop_name]["enum_values"] = prop_details["enum"]

                all_queryables[prop_name] = {
                    k: v for k, v in all_queryables[prop_name].items() if v is not None
                }

            return (
                collection.id,
                CollectionQueryables(
                    id=collection.id,
                    title=collection.title,
                    description=collection.description,
                    all_queryables=all_queryables,
                    enum_queryables=enum_queryables,
                    has_enum_filters=len(enum_queryables) > 0,
                    total_queryables=len(all_queryables),
                    enum_count=len(enum_queryables),
                ),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            collection_data_pairs = list(zip(collection_ids, raw_queryables))
            processed = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: [
                    process_single_collection_queryables(coll_id, data)
                    for coll_id, data in collection_data_pairs
                    if coll_id in collections_map
                ],
            )

        return {coll_id: queryables for coll_id, queryables in processed}

    async def initialise(self):
        """Initialise the aiohttp session if not already created"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    limit=10,  
                    limit_per_host=5,  
                    ttl_dns_cache=300,  
                    force_close=False,  
                    enable_cleanup_closed=True,  
                )
            )

    async def close(self):
        """Close the session when done"""
        if self.session:
            await self.session.close()
            self.session = None
            self._cached_openapi_spec = None
            self._cached_collections = None

    async def get_api_key(self) -> str:
        """Get the OS API key from environment variable or init param."""
        if self.api_key:
            return self.api_key

        api_key = os.environ.get("OS_API_KEY")
        if not api_key:
            raise ValueError("OS_API_KEY environment variable is not set")
        return api_key

    async def make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        path_params: Optional[List[str]] = None,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Make a request to the OS NGD API with proper error handling.

        Args:
            endpoint: Enum endpoint to use
            params: Additional query parameters
            path_params: Parameters to format into the URL path
            max_retries: Maximum number of retries for transient errors

        Returns:
            JSON response as dictionary
        """
        await self.initialise()

        if self.session is None:
            raise ValueError("Session not initialised")

        async with self._request_semaphore:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - self.last_request_time
            if elapsed < self.request_delay:
                await asyncio.sleep(self.request_delay - elapsed)

            try:
                endpoint_value = NGDAPIEndpoint[endpoint].value
            except KeyError:
                raise ValueError(f"Invalid endpoint: {endpoint}")

            if path_params:
                endpoint_value = endpoint_value.format(*path_params)

            api_key = await self.get_api_key()
            request_params = params or {}
            request_params["key"] = api_key

            headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

            client_ip = getattr(self.session, "_source_address", None)
            client_info = f" from {client_ip}" if client_ip else ""

            sanitized_url = self._sanitise_api_key(endpoint_value)
            logger.info(f"Requesting URL: {sanitized_url}{client_info}")

            for attempt in range(1, max_retries + 1):
                try:
                    self.last_request_time = asyncio.get_event_loop().time()

                    timeout = aiohttp.ClientTimeout(total=30.0)
                    async with self.session.get(
                        endpoint_value,
                        params=request_params,
                        headers=headers,
                        timeout=timeout,
                    ) as response:
                        if response.status >= 400:
                            error_text = await response.text()
                            sanitized_error = self._sanitise_api_key(error_text)
                            error_message = (
                                f"HTTP Error: {response.status} - {sanitized_error}"
                            )
                            logger.error(f"Error: {error_message}")
                            raise ValueError(error_message)

                        response_data = await response.json()

                        return self._sanitise_response(response_data)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt == max_retries:
                        sanitized_exception = self._sanitise_api_key(str(e))
                        error_message = f"Request failed after {max_retries} attempts: {sanitized_exception}"
                        logger.error(f"Error: {error_message}")
                        raise ValueError(error_message)
                    else:
                        await asyncio.sleep(0.5 * attempt)
                except Exception as e:
                    sanitized_exception = self._sanitise_api_key(str(e))
                    error_message = f"Request failed: {sanitized_exception}"
                    logger.error(f"Error: {error_message}")
                    raise ValueError(error_message)
            raise RuntimeError(
                "Unreachable: make_request exited retry loop without returning or raising"
            )

    async def make_request_no_auth(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> str:
        """
        Make a request without authentication (for public endpoints like documentation).

        Args:
            url: Full URL to request
            params: Additional query parameters
            max_retries: Maximum number of retries for transient errors

        Returns:
            Response text (not JSON parsed)
        """
        await self.initialise()

        if self.session is None:
            raise ValueError("Session not initialised")

        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)

        request_params = params or {}
        headers = {"User-Agent": self.user_agent}

        logger.info(f"Requesting URL (no auth): {url}")

        for attempt in range(1, max_retries + 1):
            try:
                self.last_request_time = asyncio.get_event_loop().time()

                timeout = aiohttp.ClientTimeout(total=30.0)
                async with self.session.get(
                    url,
                    params=request_params,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        error_message = f"HTTP Error: {response.status} - {error_text}"
                        logger.error(f"Error: {error_message}")
                        raise ValueError(error_message)

                    return await response.text()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == max_retries:
                    error_message = (
                        f"Request failed after {max_retries} attempts: {str(e)}"
                    )
                    logger.error(f"Error: {error_message}")
                    raise ValueError(error_message)
                else:
                    await asyncio.sleep(0.7)
            except Exception as e:
                error_message = f"Request failed: {str(e)}"
                logger.error(f"Error: {error_message}")
                raise ValueError(error_message)

        raise RuntimeError(
            "Unreachable: make_request_no_auth exited retry loop without returning or raising"
        )
