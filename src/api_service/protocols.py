from typing import Protocol, Dict, List, Any, Optional, runtime_checkable
from models import (
    OpenAPISpecification,
    CollectionsCache,
    WorkflowContextCache,
    CollectionQueryables,
)


@runtime_checkable
class APIClient(Protocol):
    """Protocol for API clients"""

    async def initialise(self):
        """Initialise the aiohttp session if not already created"""
        ...

    async def close(self):
        """Close the aiohttp session"""
        ...

    async def get_api_key(self) -> str:
        """Get the API key"""
        ...

    async def make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        path_params: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Make a request to an API endpoint"""
        ...

    async def make_request_no_auth(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> str:
        """Make a request without authentication"""
        ...

    async def cache_openapi_spec(self) -> OpenAPISpecification:
        """Cache the OpenAPI spec"""
        ...

    async def cache_collections(self) -> CollectionsCache:
        """Cache the collections data"""
        ...

    async def cache_workflow_context(self) -> WorkflowContextCache:
        """Cache the workflow context data"""
        ...

    async def fetch_collections_queryables(
        self, collection_ids: List[str]
    ) -> Dict[str, CollectionQueryables]:
        """Fetch detailed queryables for specific collections only"""
        ...
