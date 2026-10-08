"""Deployment contracts for the replaceable Gateway boundary."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_organization_catalogs_and_app_calls_use_gateway_in_both_modes():
    for mode in ("dev", "prod"):
        services = yaml.safe_load((ROOT / f"deploy/docker/docker-compose-{mode}.yml").read_text())[
            "services"
        ]
        assert services["user-service"]["environment"]["GATEWAY_URL"] == "http://apisix:8000"
        expected = {
            "agent-service": [
                "INTERNAL_USER_SERVICE_URL",
                "INTERNAL_TOOLS_SERVICE_URL",
                "INTERNAL_RAG_SERVICE_API_URL",
            ],
            "tools-service": [
                "INTERNAL_USER_SERVICE_URL",
                "INTERNAL_AGENT_SERVICE_URL",
                "INTERNAL_RAG_SERVICE_API_URL",
            ],
            "rag-service": ["INTERNAL_USER_SERVICE_URL"],
        }
        for service, variables in expected.items():
            for variable in variables:
                assert services[service]["environment"][variable].startswith("http://apisix:8000/")
        for name in ("user-service", "agent-service", "rag-service", "tools-service"):
            for binding in services[name].get("ports", []):
                assert binding.startswith("127.0.0.1:"), "Backend debug ports must not be public"


def _routes():
    return {
        r["id"]: r
        for r in yaml.safe_load((ROOT / "configs/apisix/apisix.yaml").read_text())["routes"]
    }


def test_gateway_auth_routes_terminate_in_gateway_and_public_routes_use_keycloak_policy():
    routes = _routes()
    for name in (
        "user-service-protected",
        "agent-service-protected",
        "rag-service-protected",
        "tools-service-mcp",
    ):
        assert routes[name]["plugins"]["gateway-auth"]["mode"] == "protected"
    for name in ("gateway-auth", "user-auth-session"):
        assert routes[name]["plugins"]["gateway-auth"]["mode"] == "auth"
    for name in ("user-auth-register",):
        assert routes[name]["methods"] == ["POST"]
        assert "gateway-auth" not in routes[name]["plugins"]


def test_internal_routes_authenticate_at_gateway():
    for name, route in _routes().items():
        paths = route.get("uris", [route.get("uri", "")])
        if name == "operational-endpoints-denied":
            continue
        if any(path.startswith("/internal/") for path in paths):
            assert route["plugins"]["gateway-auth"]["mode"] == "internal"


def test_bootstrap_runs_from_mounted_repository_layout():
    config = yaml.safe_load((ROOT / "deploy/docker/docker-compose-services.yml").read_text())
    bootstrap = config["services"]["keycloak-bootstrap"]
    assert "../../scripts:/workspace/scripts:ro" in bootstrap["volumes"]
    assert "/workspace/scripts/bootstrap_keycloak.sh" in bootstrap["command"][-1]
    assert config["services"]["apisix"]["depends_on"]["keycloak-bootstrap"] == {
        "condition": "service_completed_successfully"
    }
    assert (
        bootstrap["environment"]["GATEWAY_KEYCLOAK_CLIENT_ID"] == "${GATEWAY_KEYCLOAK_CLIENT_ID:?Set the Gateway Keycloak client ID}"
    )
    for mode in ("dev", "prod"):
        service = yaml.safe_load((ROOT / f"deploy/docker/docker-compose-{mode}.yml").read_text())[
            "services"
        ]["user-service"]
        for name in ("REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD"):
            assert service["environment"][name] == bootstrap["environment"][name]


def test_only_the_gateway_with_trusted_identity_is_active():
    config = yaml.safe_load((ROOT / "deploy/docker/docker-compose-services.yml").read_text())
    assert "kong" not in config["services"]
    assert (
        "gateway-auth"
        in yaml.safe_load((ROOT / "configs/apisix/config.yaml").read_text())["plugins"]
    )


def test_gateway_preserves_streaming_routes():
    for name in ("agent-service-protected", "tools-service-mcp", "internal-tools-service"):
        assert _routes()[name]["plugins"]["proxy-buffering"]["disable_proxy_buffering"] is True
    assert (
        "proxy_request_buffering off;"
        in yaml.safe_load((ROOT / "configs/apisix/config.yaml").read_text())["nginx_config"][
            "http_configuration_snippet"
        ]
    )


def test_connector_tool_paths_preserve_suffixes():
    route = _routes()["internal-agent-connector-tools"]
    assert route["methods"] == ["POST"]
    assert route["uris"][1] == route["uris"][0] + "/*"
    assert route["plugins"]["proxy-rewrite"]["regex_uri"] == [
        "^/internal/agent-service/(.*)",
        "/$1",
    ]
