import os
from pathlib import Path

import pytest
from localization import init_localization

init_localization(Path(__file__).resolve().parents[1] / "locales")

# The application is constructed at import time by several test modules, so the
# settings it reads must exist before any of them import ``server``.
os.environ["INTERNAL_AGENT_SERVICE_URL"] = "http://apisix:8000/internal/agent-service/api/v1"
os.environ["INTERNAL_RAG_SERVICE_API_URL"] = "http://apisix:8000/internal/rag-service"
os.environ.setdefault("MCP_HOST", "127.0.0.1")
os.environ.setdefault("MCP_PORT", "9000")
os.environ.setdefault("INTERNAL_USER_SERVICE_URL", "http://apisix:8000/internal/user-service")
os.environ.setdefault("POSTGRES_HOST", "postgres")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_TOOL_SERVICE_USER", "tools")
os.environ.setdefault("POSTGRES_TOOL_SERVICE_PASSWORD", "secret")
os.environ.setdefault("POSTGRES_TOOL_SERVICE_DB", "tools")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")


@pytest.fixture(scope="session")
def http_app():
    """The tools-service FastAPI application.

    Deliberately the module-level instance rather than a fresh build: the MCP
    session manager belongs to the module-level ``FastMCP`` object and refuses to
    start twice, so the whole session must share one application and one lifespan.
    """
    import server

    return server.app


@pytest.fixture(scope="session")
def http_client(http_app):
    """A client with the application lifespan entered exactly once."""
    from fastapi.testclient import TestClient

    with TestClient(http_app) as client:
        yield client
