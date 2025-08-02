from typing import Protocol, Optional, Callable, List, runtime_checkable, Any


@runtime_checkable
class MCPService(Protocol):
    """Protocol for MCP services"""

    def tool(self) -> Callable[..., Any]:
        """Register a function as an MCP tool"""
        ...

    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
    ) -> Callable[[Any], Any]:
        """Register a function as an MCP resource"""
        ...

    def run(self) -> None:
        """Run the MCP service"""
        ...


@runtime_checkable
class FeatureService(Protocol):
    """Protocol for OS NGD feature services"""

    def hello_world(self, name: str) -> str:
        """Test connection to the service"""
        ...

    def check_api_key(self) -> str:
        """Check if API key is available"""
        ...

    async def list_collections(self) -> str:
        """List all available feature collections"""
        ...

    async def get_single_collection(self, collection_id: str) -> str:
        """Get detailed information about a specific collection"""
        ...

    async def get_single_collection_queryables(self, collection_id: str) -> str:
        """Get queryable properties for a collection"""
        ...

    # TODO: Need to make sure the full list of parameters is supported
    # TODO: Supporting cql-text is clunky and need to figure out how to support this better
    async def search_features(
        self,
        collection_id: str,
        bbox: Optional[str] = None,
        crs: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        filter: Optional[str] = None,
        filter_lang: Optional[str] = "cql-text",
        query_attr: Optional[str] = None,
        query_attr_value: Optional[str] = None,
    ) -> str:
        """Search for features in a collection with full CQL filter support"""
        ...

    async def get_feature(
        self, collection_id: str, feature_id: str, crs: Optional[str] = None
    ) -> str:
        """Get a specific feature by ID"""
        ...

    async def get_linked_identifiers(
        self, identifier_type: str, identifier: str, feature_type: Optional[str] = None
    ) -> str:
        """Get linked identifiers for a specified identifier"""
        ...

    async def get_bulk_features(
        self,
        collection_id: str,
        identifiers: List[str],
        query_by_attr: Optional[str] = None,
    ) -> str:
        """Get multiple features in a single call"""
        ...

    async def get_bulk_linked_features(
        self,
        identifier_type: str,
        identifiers: List[str],
        feature_type: Optional[str] = None,
    ) -> str:
        """Get linked features for multiple identifiers"""
        ...

    async def fetch_detailed_collections(self, collection_ids: List[str]) -> str:
        """Get detailed information about specific collections for workflow planning"""
        ...
