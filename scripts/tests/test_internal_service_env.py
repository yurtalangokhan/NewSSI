"""Deployment URL overrides keep backend traffic on internal gateway routes."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INTERNAL_URLS = {
    "agent-service": {
        "INTERNAL_TOOLS_SERVICE_URL": "/internal/tools-service/mcp",
        "INTERNAL_RAG_SERVICE_API_URL": "/internal/rag-service",
        "INTERNAL_USER_SERVICE_URL": "/internal/user-service",
    },
    "rag-service": {"INTERNAL_USER_SERVICE_URL": "/internal/user-service"},
    "tools-service": {
        "INTERNAL_USER_SERVICE_URL": "/internal/user-service",
        "INTERNAL_RAG_SERVICE_API_URL": "/internal/rag-service",
        "INTERNAL_AGENT_SERVICE_URL": "/internal/agent-service/api/v1",
    },
}


@pytest.mark.parametrize("mode", ["dev", "prod"])
def test_backend_compose_urls_use_internal_gateway_routes(mode):
    compose = yaml.safe_load(
        (ROOT / f"deploy/docker/docker-compose-{mode}.yml").read_text()
    )
    for service, urls in INTERNAL_URLS.items():
        environment = compose["services"][service].get("environment", {})
        for key, path in urls.items():
            assert environment.get(key) == f"http://apisix:8000{path}", (service, key)
            assert key.removeprefix("INTERNAL_") not in environment


def test_web_compose_user_url_remains_public():
    compose = yaml.safe_load(
        (ROOT / "deploy/docker/docker-compose-dev.yml").read_text()
    )
    assert compose["services"]["web"]["environment"]["USER_SERVICE_URL"] == (
        "http://apisix:8000/user-service"
    )
