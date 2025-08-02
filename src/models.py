"""
Types for the OS NGD API MCP Server
"""

from enum import Enum
from pydantic import BaseModel
from typing import Any, List, Dict


class NGDAPIEndpoint(Enum):
    """
    Enum for the OS API Endpoints following OGC API Features standard
    """

    # NGD Features Endpoints
    NGD_FEATURES_BASE_PATH = "https://api.os.uk/features/ngd/ofa/v1/{}"
    COLLECTIONS = NGD_FEATURES_BASE_PATH.format("collections")
    COLLECTION_INFO = NGD_FEATURES_BASE_PATH.format("collections/{}")
    COLLECTION_SCHEMA = NGD_FEATURES_BASE_PATH.format("collections/{}/schema")
    COLLECTION_FEATURES = NGD_FEATURES_BASE_PATH.format("collections/{}/items")
    COLLECTION_FEATURE_BY_ID = NGD_FEATURES_BASE_PATH.format("collections/{}/items/{}")
    COLLECTION_QUERYABLES = NGD_FEATURES_BASE_PATH.format("collections/{}/queryables")

    # OpenAPI Specification Endpoint
    OPENAPI_SPEC = NGD_FEATURES_BASE_PATH.format("api")

    # Linked Identifiers Endpoints
    LINKED_IDENTIFIERS_BASE_PATH = "https://api.os.uk/search/links/v1/{}"
    LINKED_IDENTIFIERS = LINKED_IDENTIFIERS_BASE_PATH.format("identifierTypes/{}/{}")

    # Markdown Resources
    MARKDOWN_BASE_PATH = "https://docs.os.uk/osngd/data-structure/{}"
    MARKDOWN_STREET = MARKDOWN_BASE_PATH.format("transport/transport-network/street.md")
    MARKDOWN_ROAD = MARKDOWN_BASE_PATH.format("transport/transport-network/road.md")
    TRAM_ON_ROAD = MARKDOWN_BASE_PATH.format(
        "transport/transport-network/tram-on-road.md"
    )
    ROAD_NODE = MARKDOWN_BASE_PATH.format("transport/transport-network/road-node.md")
    ROAD_LINK = MARKDOWN_BASE_PATH.format("transport/transport-network/road-link.md")
    ROAD_JUNCTION = MARKDOWN_BASE_PATH.format(
        "transport/transport-network/road-junction.md"
    )

    # Places API Endpoints
    # TODO: Add these back in when I get access to the Places API from OS
    # PLACES_BASE_PATH = "https://api.os.uk/search/places/v1/{}"
    # PLACES_UPRN = PLACES_BASE_PATH.format("uprn")
    # POST_CODE = PLACES_BASE_PATH.format("postcode")


class OpenAPISpecification(BaseModel):
    """Parsed OpenAPI specification optimized for LLM context"""

    title: str
    version: str
    base_url: str
    endpoints: Dict[str, str]
    collection_ids: List[str]
    supported_crs: Dict[str, Any]
    crs_guide: Dict[str, str]


class WorkflowStep(BaseModel):
    """A single step in a workflow plan"""

    step_number: int
    description: str
    api_endpoint: str
    parameters: Dict[str, Any]
    dependencies: List[int] = []


class WorkflowPlan(BaseModel):
    """Generated workflow plan for user requests"""

    user_request: str
    steps: List[WorkflowStep]
    reasoning: str
    estimated_complexity: str = "simple"


class Collection(BaseModel):
    """Represents a feature collection from the OS NGD API"""

    id: str
    title: str
    description: str = ""
    links: List[Dict[str, Any]] = []
    extent: Dict[str, Any] = {}
    itemType: str = "feature"


class CollectionsCache(BaseModel):
    """Cached collections data with filtering applied"""

    collections: List[Collection]
    raw_response: Dict[str, Any]


class CollectionQueryables(BaseModel):
    """Queryables information for a collection"""

    id: str
    title: str
    description: str
    all_queryables: Dict[str, Any]
    enum_queryables: Dict[str, Any]
    has_enum_filters: bool
    total_queryables: int
    enum_count: int


class WorkflowContextCache(BaseModel):
    """Cached workflow context data"""

    collections_info: Dict[str, CollectionQueryables]
    openapi_spec: OpenAPISpecification
    cached_at: float
