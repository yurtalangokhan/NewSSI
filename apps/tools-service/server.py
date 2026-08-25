"""
MCP Server with HTTP transport for Open Agent Platform.
Uses FastMCP for simple tool definitions with modular plugin architecture.
Provides tools for web search, calculations, utilities, and more.
"""

import contextlib
import sys
from pathlib import Path

from error_contract import ErrorContractMiddleware
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Suppress WinError 10054 (connection reset by peer) on Windows.
# This is a known asyncio ProactorEventLoop issue when HTTP/SSE clients
# disconnect — the socket is already closed by the time the server tries
# to shut it down, which is harmless but noisy.
if sys.platform == "win32":
    import asyncio.proactor_events as _pe

    _orig_call_connection_lost = _pe._ProactorBasePipeTransport._call_connection_lost

    def _patched_call_connection_lost(self, exc):
        with contextlib.suppress(ConnectionResetError, OSError):
            _orig_call_connection_lost(self, exc)

    _pe._ProactorBasePipeTransport._call_connection_lost = _patched_call_connection_lost

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from i18n import I18nMiddleware, init_service_i18n
from idempotency import IdempotencyMiddleware

from src.core.auth import KeycloakTokenVerifier
from src.core.database import close_db_pool
from src.core.idempotency import build_idempotency_config, build_idempotency_exclude_paths
from src.core.registry import ToolRegistry
from src.core.settings import get_settings

locales_dir = Path(__file__).parent / "locales"
init_service_i18n(locales_dir)

# Initialize FastMCP server
mcp = FastMCP("open-agent-tools", auth=KeycloakTokenVerifier())


@mcp.custom_route("/health", methods=["GET"], name="health", include_in_schema=True)
async def health_check(request: Request) -> Response:
    """Public health check endpoint outside the MCP protocol transport."""
    return JSONResponse({"status": "ok"})


# Initialize the tool registry with plugin discovery
registry = ToolRegistry(mcp)

# Discover and register all tool categories from src/tools/
plugins_dir = Path(__file__).parent / "src" / "tools"
registry.discover_plugins(str(plugins_dir))


# Cleanup hook for graceful shutdown
async def cleanup():
    """Cleanup resources on shutdown."""
    await registry.cleanup_all()
    await close_db_pool()


def build_idempotency_middleware() -> list[Middleware]:
    """Build service middleware for the FastMCP HTTP app."""
    settings = get_settings()
    return [
        Middleware(ErrorContractMiddleware, service_name="tools-service"),
        Middleware(I18nMiddleware),
        Middleware(
            IdempotencyMiddleware,
            config=build_idempotency_config(settings),
            exclude_paths=build_idempotency_exclude_paths(),
        ),
    ]


def build_http_app():
    """Build the FastMCP HTTP ASGI app with service middleware."""
    return mcp.http_app(
        transport="http",
        middleware=build_idempotency_middleware(),
    )


# Run with HTTP transport for Open Agent Platform compatibility
if __name__ == "__main__":
    settings = get_settings()
    port = settings.mcp_port
    host = settings.mcp_host

    print(f"\n{'=' * 60}")
    print("MCP Server - Modular Architecture")
    print(f"{'=' * 60}")
    print(f"Starting FastMCP Server on http://{host}:{port}")
    print(f"MCP endpoint: http://{host}:{port}/mcp")
    print(f"{'=' * 60}\n")

    # Use HTTP transport (serves at /mcp endpoint)
    mcp.run(
        transport="http",
        host=host,
        port=port,
        middleware=build_idempotency_middleware(),
    )
