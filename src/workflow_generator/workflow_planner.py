from typing import Dict, Any, Optional, List
from models import OpenAPISpecification
from utils.logging_config import get_logger

logger = get_logger(__name__)


class WorkflowPlanner:
    """Context provider for LLM workflow planning"""

    def __init__(
        self,
        openapi_spec: Optional[OpenAPISpecification],
        basic_collections_info: Optional[Dict[str, Any]] = None,
    ):
        self.spec = openapi_spec
        self.basic_collections_info = basic_collections_info or {}
        self.detailed_collections_cache = {}

    def get_basic_context(self) -> Dict[str, Any]:
        """Get basic context for LLM to plan its workflow - no detailed queryables"""
        return {
            "available_collections": self.basic_collections_info,
            "openapi_spec": self.spec,
        }

    def get_detailed_context(self, collection_ids: List[str]) -> Dict[str, Any]:
        """Get detailed context for specific collections mentioned in the plan"""
        detailed_collections = {
            coll_id: self.detailed_collections_cache.get(coll_id)
            for coll_id in collection_ids
            if coll_id in self.detailed_collections_cache
        }

        return {
            "available_collections": detailed_collections,
            "openapi_spec": self.spec,
        }
