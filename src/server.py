import argparse
import os
import uvicorn

from typing import Any
from utils.logging_config import configure_logging
from api_service.os_api import OSAPIClient
from mcp_service.os_service import OSDataHubService
from mcp.server.fastmcp import FastMCP
from middleware.stdio_middleware import StdioMiddleware
from middleware.http_middleware import HTTPMiddleware
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route
from starlette.responses import JSONResponse

logger = configure_logging()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="OS DataHub API MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use (stdio or streamable-http)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    logger.info(
        f"OS DataHub API MCP Server starting with {args.transport} transport..."
    )

    api_client = OSAPIClient()

    match args.transport:
        case "stdio":
            logger.info("Starting with stdio transport")

            mcp = FastMCP(
                "os-ngd-api",
                debug=args.debug,
                log_level="DEBUG" if args.debug else "INFO",
            )

            stdio_auth = StdioMiddleware()

            service = OSDataHubService(api_client, mcp, stdio_middleware=stdio_auth)

            stdio_api_key = os.environ.get("STDIO_KEY")
            if not stdio_api_key or not stdio_auth.authenticate(stdio_api_key):
                logger.error("Authentication failed")
                return

            service.run()

        case "streamable-http":
            logger.info(f"Starting Streamable HTTP server on {args.host}:{args.port}")

            mcp = FastMCP(
                "os-ngd-api",
                host=args.host,
                port=args.port,
                debug=args.debug,
                json_response=True,
                stateless_http=False,
                log_level="DEBUG" if args.debug else "INFO",
            )

            OSDataHubService(api_client, mcp)

            async def auth_discovery(_: Any) -> JSONResponse:
                """Return authentication methods."""
                return JSONResponse(
                    content={"authMethods": [{"type": "http", "scheme": "bearer"}]}
                )

            app = mcp.streamable_http_app()

            app.routes.append(
                Route(
                    "/.well-known/mcp-auth",
                    endpoint=auth_discovery,
                    methods=["GET"],
                )
            )

            app.user_middleware.extend(
                [
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],
                        allow_credentials=True,
                        allow_methods=["GET", "POST", "OPTIONS"],
                        allow_headers=["*"],
                        expose_headers=["*"],
                    ),
                    Middleware(HTTPMiddleware),
                ]
            )

            uvicorn.run(
                app,
                host=args.host,
                port=args.port,
                log_level="debug" if args.debug else "info",
            )

        case _:
            logger.error(f"Unknown transport: {args.transport}")
            return


if __name__ == "__main__":
    main()
