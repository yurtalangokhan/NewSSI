from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_connector_resolution_gateway_exposes_only_internal_connector_path():
    config = yaml.safe_load((ROOT / "configs/kong/kong.yml").read_text())
    service = next(s for s in config["services"] if s["name"] == "internal-agent-connector-tools")
    assert service["url"] == "__AGENT_SERVICE_UPSTREAM_URL__/api/v1/internal/connector-tools"
    assert service["routes"][0]["paths"] == ["/internal/agent-service/api/v1/internal/connector-tools"]
    assert service["routes"][0]["methods"] == ["POST"]


def test_tools_service_has_configured_agent_resolution_url_in_both_environments():
    for name in ("dev", "prod"):
        config = yaml.safe_load((ROOT / f"configs/docker-compose-{name}.yml").read_text())
        assert config["services"]["tools-service"]["environment"]["AGENT_SERVICE_URL"].endswith(
            "/internal/agent-service/api/v1"
        )
