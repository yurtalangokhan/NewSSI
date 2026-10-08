from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_connector_resolution_gateway_exposes_only_internal_connector_path():
    config = yaml.safe_load((ROOT / "configs/apisix/apisix.yaml").read_text())
    route = next(r for r in config["routes"] if r["name"] == "internal-agent-connector-tools")
    assert route["uris"] == [
        "/internal/agent-service/api/v1/internal/connector-tools",
        "/internal/agent-service/api/v1/internal/connector-tools/*",
    ]
    assert route["methods"] == ["POST"]
    assert route["upstream_id"] == "agent-service"
    # APISIX rewrites the gateway prefix off the path: the upstream sees
    # /api/v1/internal/connector-tools[/...], the service's own path.
    assert route["plugins"]["proxy-rewrite"]["regex_uri"] == ["^/internal/agent-service/(.*)", "/$1"]
    assert route["plugins"]["gateway-auth"]["mode"] == "internal"


def test_tools_service_has_configured_agent_resolution_url_in_both_environments():
    for name in ("dev", "prod"):
        config = yaml.safe_load((ROOT / f"deploy/docker/docker-compose-{name}.yml").read_text())
        environment = config["services"]["tools-service"]["environment"]
        assert environment["INTERNAL_AGENT_SERVICE_URL"].endswith("/internal/agent-service/api/v1")
