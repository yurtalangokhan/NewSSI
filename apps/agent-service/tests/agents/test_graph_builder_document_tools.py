"""Tests for always-on document tool injection into GraphBuilder-built graphs.

Document tools (create_document, create_spreadsheet) are not opt-in MCP tools —
they must be present on every react/plan-execute/sub-agent graph GraphBuilder
produces, unless disabled via settings.

**Zero-shot is the exception.** It used to be upgraded to a react agent purely
because document tools exist, which made a component documented as "a single
model call with a system prompt, no tools" call tools — the two agent kinds
collapsed into one and the caller's system prompt was silently extended with
DOCUMENT_TOOL_PROMPT. A zero-shot graph now stays a single model call.
"""

from types import SimpleNamespace

from agents.document_tools import DOCUMENT_TOOL_PROMPT
from agents.graphs.builder import GraphBuilder


def _fake_document_tools() -> list[SimpleNamespace]:
    return [SimpleNamespace(name="create_document"), SimpleNamespace(name="create_spreadsheet")]


def test_build_react_includes_document_tools_and_prompt(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_agent", fake_create_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    tool_names = {t.name for t in captured["tools"]}
    assert {"create_document", "create_spreadsheet"} <= tool_names
    assert DOCUMENT_TOOL_PROMPT in captured["system_prompt"]


def test_build_react_skips_document_tools_when_disabled(monkeypatch):
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_agent", fake_create_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", lambda: [])

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful."})

    assert captured["tools"] == []
    assert DOCUMENT_TOOL_PROMPT not in captured["system_prompt"]


def test_build_zero_shot_stays_plain_even_when_document_tools_exist(monkeypatch):
    """Document tools alone must not turn a zero-shot graph into a react agent.

    "Zero-shot" means one model call with a system prompt; a tool loop is what
    ReActAgent is for. The silent upgrade made a Flow canvas ZeroShotAgent emit
    PDFs from a prompt that only asked for a one-sentence summary.
    """
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    def fail_if_called(self, config):
        raise AssertionError("_build_react should not be called for a tool-less zero-shot")

    monkeypatch.setattr(GraphBuilder, "_build_react", fail_if_called)

    class FakeModel:
        async def ainvoke(self, messages):
            return object()

    builder = GraphBuilder(model=FakeModel())
    assert builder._build_zero_shot({}) is not None


def test_build_zero_shot_still_upgrades_when_tools_are_explicitly_attached(monkeypatch):
    """An explicitly attached tool is the caller asking for a tool loop, so the
    upgrade still happens — but document tools must not ride along."""
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    called: dict = {}

    def fake_build_react(self, config):
        called["config"] = config
        return "react-graph"

    monkeypatch.setattr(GraphBuilder, "_build_react", fake_build_react)

    builder = GraphBuilder(model=object())
    assert builder._build_zero_shot({"mcp_tools": ["search"]}) == "react-graph"
    assert called["config"].get("document_tools") is False


def test_build_react_honours_the_document_tools_opt_out(monkeypatch):
    """The flag zero-shot delegation sets: no document tools, no added prompt."""
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agents.graphs.builder.create_agent", fake_create_agent)
    monkeypatch.setattr("agents.graphs.builder.get_document_tools", _fake_document_tools)

    builder = GraphBuilder(model=object())
    builder._build_react({"system_prompt": "Be helpful.", "document_tools": False})

    assert {t.name for t in captured["tools"]}.isdisjoint({"create_document", "create_spreadsheet"})
    assert DOCUMENT_TOOL_PROMPT not in captured["system_prompt"]


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
