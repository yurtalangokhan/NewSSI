"""The attachment manifest must reach the graphs production actually builds.

Same rule as ``clarification/test_wiring_on_the_live_path.py``: pin the wiring on the
path ``GraphBuilder.build_async`` takes, per schema. Only a graph whose model owns
``list_attachments`` can embed an image, so only those get the manifest.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
import pytest

from agents.graphs.builder import GraphBuilder
from agents.graphs.middleware import AttachmentManifestMiddleware
from agents.graphs.strategies.base import GraphSchemaStrategy
from agents.tooling import attachment_manifest as manifest
from core.types.authored_documents import AttachmentImageInfo

CONFIG = {"configurable": {"user_id": "u1", "thread_id": str(uuid4())}}


class Store:
    async def list_for_thread(self, user_id, thread_id):
        return [AttachmentImageInfo(file_id="f1", filename="m5.jpg", mime_type="image/jpeg")]


def _capture(monkeypatch, module_path: str, factory: str) -> dict:
    captured: dict = {}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(f"{module_path}.{factory}", fake_factory)
    return captured


def _stub_supervisor(monkeypatch) -> None:
    monkeypatch.setattr(
        "langgraph_supervisor.create_supervisor",
        lambda agents, **_kwargs: SimpleNamespace(compile=lambda **_kw: SimpleNamespace(name="compiled")),
    )


async def _prompt_messages(prompt) -> list:
    """What the model would be sent as its system message, resolved for CONFIG's chat."""
    return await prompt({"messages": [HumanMessage(content="hi")]}, CONFIG)


def _assert_manifest_aware(captured: dict) -> None:
    assert callable(captured["prompt"]) and not isinstance(captured["prompt"], SystemMessage)


async def _assert_prompt_carries_the_manifest(captured: dict, base: str) -> None:
    system, *_ = await _prompt_messages(captured["prompt"])
    assert base in system.content
    assert "attachment:f1" in system.content


@pytest.fixture(autouse=True)
def _one_attached_image(monkeypatch):
    monkeypatch.setattr(manifest, "attachment_store", lambda: Store())


class TestReActStrategy:
    @pytest.mark.asyncio
    async def test_the_middleware_is_installed_outermost(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

        await GraphBuilder(model=object()).build_async("react", {"system_prompt": "Be helpful."})

        assert isinstance(captured["middleware"][0], AttachmentManifestMiddleware)

    @pytest.mark.asyncio
    async def test_a_graph_without_document_tools_gets_no_manifest(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

        await GraphBuilder(model=object()).build_async(
            "react", {"system_prompt": "Be helpful.", "document_tools": False}
        )

        assert not any(isinstance(m, AttachmentManifestMiddleware) for m in captured["middleware"])


class TestCreateReactAgentStrategies:
    @pytest.mark.asyncio
    async def test_plan_execute(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "agents.graphs.strategies.plan_execute", "create_react_agent")

        await GraphBuilder(model=object()).build_async("plan_execute", {"system_prompt": "Be helpful."})

        _assert_manifest_aware(captured)
        await _assert_prompt_carries_the_manifest(captured, "Be helpful.")

    @pytest.mark.asyncio
    async def test_a_supervisor_sub_agent(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "langgraph.prebuilt", "create_react_agent")
        _stub_supervisor(monkeypatch)

        await GraphBuilder(model=object()).build_async(
            "supervisor",
            {"system_prompt": "Coordinate.", "sub_agents": [{"name": "worker", "system_prompt": "Work."}]},
        )

        _assert_manifest_aware(captured)
        await _assert_prompt_carries_the_manifest(captured, "Work.")

    @pytest.mark.asyncio
    async def test_a_pipeline_stage(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "langgraph.prebuilt", "create_react_agent")
        _stub_supervisor(monkeypatch)

        await GraphBuilder(model=object()).build_async(
            "pipeline",
            {"pipeline_prompt": "Run in order.", "stages": [{"name": "step-one", "system_prompt": "Do."}]},
        )

        _assert_manifest_aware(captured)
        await _assert_prompt_carries_the_manifest(captured, "Do.")

    @pytest.mark.asyncio
    async def test_without_document_tools_the_prompt_stays_static(self, monkeypatch) -> None:
        monkeypatch.setattr(GraphSchemaStrategy, "_get_document_tools", lambda self: [])
        captured = _capture(monkeypatch, "agents.graphs.strategies.plan_execute", "create_react_agent")

        await GraphBuilder(model=object()).build_async("plan_execute", {"system_prompt": "Be helpful."})

        assert isinstance(captured["prompt"], SystemMessage)
        assert "attachment:" not in captured["prompt"].content


class TestConfigurableAgent:
    """The default chat path: its graph is cached, so the manifest must be per call."""

    @staticmethod
    def _build(monkeypatch, document_tools: list) -> dict:
        from agents.implementations.configurable_mcp_agent import ConfigurableMCPAgent

        captured = _capture(monkeypatch, "agents.implementations.configurable_mcp_agent", "create_react_agent")
        monkeypatch.setattr("agents.implementations.configurable_mcp_agent.get_model", lambda _model: object())
        monkeypatch.setattr(
            "agents.implementations.configurable_mcp_agent.get_document_tools", lambda: document_tools
        )
        ConfigurableMCPAgent()._create_agent_graph(system_prompt="Be helpful.", mcp_tool_names=[])
        return captured

    @pytest.mark.asyncio
    async def test_a_graph_with_list_attachments_carries_the_manifest(self, monkeypatch) -> None:
        from agents.tooling.document_tools import DOCUMENT_TOOL_PROMPT, list_attachments, list_documents

        captured = self._build(monkeypatch, [list_documents, list_attachments])

        _assert_manifest_aware(captured)
        await _assert_prompt_carries_the_manifest(captured, DOCUMENT_TOOL_PROMPT)

    def test_a_graph_without_it_keeps_the_static_prompt(self, monkeypatch) -> None:
        captured = self._build(monkeypatch, [])

        assert isinstance(captured["prompt"], SystemMessage)
