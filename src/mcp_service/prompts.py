from typing import List
from mcp.types import PromptMessage, TextContent
from prompt_templates.prompt_templates import PROMPT_TEMPLATES
from utils.logging_config import get_logger

logger = get_logger(__name__)


class OSWorkflowPrompts:
    """Handles registration of OS NGD workflow prompts"""

    def __init__(self, mcp_service):
        self.mcp = mcp_service

    def register_all(self) -> None:
        """Register all workflow prompts"""
        self._register_analysis_prompts()
        self._register_general_prompts()

    def _register_analysis_prompts(self) -> None:
        """Register analysis workflow prompts"""

        @self.mcp.prompt()
        def usrn_breakdown_analysis(usrn: str) -> List[PromptMessage]:
            """Generate a step-by-step USRN breakdown workflow"""
            template = PROMPT_TEMPLATES["usrn_breakdown"].format(usrn=usrn)

            return [
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"As an expert in OS NGD API workflows and transport network analysis, {template}",
                    ),
                )
            ]

    def _register_general_prompts(self) -> None:
        """Register general OS NGD guidance prompts"""

        @self.mcp.prompt()
        def collection_query_guidance(
            collection_id: str, query_type: str = "features"
        ) -> List[PromptMessage]:
            """Generate guidance for querying OS NGD collections"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"As an OS NGD API expert, guide me through querying the '{collection_id}' collection for {query_type}. "
                        f"Include: 1) Available filters, 2) Best practices for bbox queries, "
                        f"3) CRS considerations, 4) Example queries with proper syntax.",
                    ),
                )
            ]

        @self.mcp.prompt()
        def workflow_planning(
            user_request: str, data_theme: str = "transport"
        ) -> List[PromptMessage]:
            """Generate a workflow plan for complex OS NGD queries"""
            return [
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"As a geospatial workflow planner, create a detailed workflow plan for: '{user_request}'. "
                        f"Focus on {data_theme} theme data. Include: "
                        f"1) Collection selection rationale, "
                        f"2) Query sequence with dependencies, "
                        f"3) Filter strategies, "
                        f"4) Error handling considerations.",
                    ),
                )
            ]
