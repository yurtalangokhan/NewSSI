"""Importing the application must not need configuration.

The Makefile smoke `docker-smoke-agent-service` runs the image with no environment at all:
`docker run --rm --entrypoint python agentic-ai-platform/agent-service:<tag> -c "import app"`.
`agents/implementations/configurable_mcp_agent.py` instantiates an agent at module scope, and
both it and `DynamicAgent` used to build their tools-service gateway in `__init__`, which
resolves `INTERNAL_TOOLS_SERVICE_URL` through `mcp_url_policy.default_mcp_url()` and raises
when it is unset. The gateway is needed on first tool resolution, not at import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agents.implementations import configurable_mcp_agent as configurable_module
from agents.implementations import dynamic_agent as dynamic_module
from agents.implementations.configurable_mcp_agent import ConfigurableMCPAgent
from agents.implementations.dynamic_agent import DynamicAgent

SRC = Path(__file__).resolve().parents[2] / "src"

# Runs in a fresh interpreter: the policy is replaced before anything imports it, so any
# import-time or construction-time resolution of the tools-service URL fails loudly, exactly
# as it does in an image started without configuration.
UNCONFIGURED_IMPORT = """
import core.security.mcp.mcp_url_policy as policy


def unconfigured() -> str:
    raise RuntimeError("INTERNAL_TOOLS_SERVICE_URL must be configured")


policy.default_mcp_url = unconfigured

import app  # noqa: E402,F401  (the smoke's statement)

from agents.implementations.configurable_mcp_agent import ConfigurableMCPAgent  # noqa: E402
from agents.implementations.dynamic_agent import DynamicAgent  # noqa: E402

for agent in (ConfigurableMCPAgent(), DynamicAgent({"name": "smoke"})):
    try:
        agent._gateway
    except RuntimeError as exc:
        assert "INTERNAL_TOOLS_SERVICE_URL" in str(exc), exc
    else:
        raise SystemExit("the gateway was built without the tools-service URL")
print("import-ok")
"""


def test_import_app_needs_no_tools_service_url():
    result = subprocess.run(
        [sys.executable, "-c", UNCONFIGURED_IMPORT],
        cwd=SRC,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr[-3000:]
    assert "import-ok" in result.stdout


def test_configurable_mcp_agent_builds_its_gateway_on_first_use(monkeypatch):
    built: list[object] = []
    monkeypatch.setattr(
        configurable_module, "_build_default_gateway", lambda: built.append(object()) or built[-1]
    )

    agent = ConfigurableMCPAgent()
    assert built == [], "the gateway was built in __init__"

    first = agent._gateway
    assert built == [first]
    assert agent._gateway is first, "the gateway must be built once"


def test_dynamic_agent_builds_its_gateway_on_first_use(monkeypatch):
    built: list[object] = []
    monkeypatch.setattr(
        dynamic_module, "_build_default_gateway", lambda: built.append(object()) or built[-1]
    )

    agent = DynamicAgent({"name": "lazy"})
    assert built == [], "the gateway was built in __init__"

    first = agent._gateway
    assert built == [first]
    assert agent._gateway is first, "the gateway must be built once"


def test_an_injected_gateway_is_used_as_is():
    injected = object()

    assert ConfigurableMCPAgent(gateway=injected)._gateway is injected  # type: ignore[arg-type]
    assert DynamicAgent({"name": "x"}, gateway=injected)._gateway is injected  # type: ignore[arg-type]
