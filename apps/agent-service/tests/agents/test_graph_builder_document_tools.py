"""Tests for always-on document tool injection into GraphBuilder-built graphs.

Document tools (create_document, create_spreadsheet) are not opt-in MCP tools —
they must be present on every react/zero-shot/plan-execute/sub-agent graph
GraphBuilder produces, unless disabled via settings.
"""

from types import SimpleNamespace

from agents.document_tools import DOCUMENT_TOOL_PROMPT
from agents.graphs.builder import GraphBuilder


def _fake_document_tools() -> list[SimpleNamespace]:
    return [SimpleNamespace(name="create_document"), SimpleNamespace(name="create_spreadsheet")]


def test_build_react_includes_document_tools_and_prompt(monkeypatch):
    captured: dict = {}

    def fake_create_react_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_react_agent", fake_create_react_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    tool_names = {t.name for t in captured["tools"]}
    assert {"create_document", "create_spreadsheet"} <= tool_names
    assert DOCUMENT_TOOL_PROMPT in captured["prompt"].content


def test_build_react_skips_document_tools_when_disabled(monkeypatch):
    captured: dict = {}

    def fake_create_react_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_react_agent", fake_create_react_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", lambda: [])

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    assert captured["tools"] == []
    assert DOCUMENT_TOOL_PROMPT not in captured["prompt"].content


def test_build_zero_shot_upgrades_to_react_when_document_tools_present(monkeypatch):
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    called: dict = {}

    def fake_build_react(self, config):
        called["config"] = config
        return "react-graph"

    monkeypatch.setattr(GraphBuilder, "_build_react", fake_build_react)

    builder = GraphBuilder(model=object())
    result = builder._build_zero_shot({})

    assert result == "react-graph"


def test_build_zero_shot_stays_plain_when_document_tools_disabled(monkeypatch):
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", lambda: [])

    def fail_if_called(self, config):
        raise AssertionError("_build_react should not be called when document tools disabled")

    monkeypatch.setattr(GraphBuilder, "_build_react", fail_if_called)

    class FakeModel:
        async def ainvoke(self, messages):
            return object()

    builder = GraphBuilder(model=FakeModel())
    graph = builder._build_zero_shot({})

    assert graph is not None


def test_build_plan_execute_includes_document_tools(monkeypatch):
    captured: dict = {}

    def fake_create_react_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_react_agent", fake_create_react_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    builder = GraphBuilder(model=object())
    builder._build_plan_execute({})

    tool_names = {t.name for t in captured["tools"]}
    assert {"create_document", "create_spreadsheet"} <= tool_names


def test_build_sub_agent_graph_includes_document_tools(monkeypatch):
    captured: dict = {}

    def fake_create_react_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_react_agent", fake_create_react_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    builder = GraphBuilder(model=object())
    builder._build_sub_agent_graph({"name": "worker", "system_prompt": "Do the task."})

    tool_names = {t.name for t in captured["tools"]}
    assert {"create_document", "create_spreadsheet"} <= tool_names
