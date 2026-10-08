"""Always-on document tool injection into the graphs GraphBuilder produces.

Document tools (create_document, create_spreadsheet) are not opt-in MCP
tools -- they must be present on every react/plan-execute/sub-agent graph,
unless disabled via settings.

**Zero-shot is the exception.** It used to be upgraded to a react agent
purely because document tools exist, which made a component documented as
"a single model call with a system prompt, no tools" call tools -- the two
agent kinds collapsed into one and the caller's system prompt was silently
extended with DOCUMENT_TOOL_PROMPT. A zero-shot graph stays a single model
call. An explicitly attached tool (an mcp_tools name, an extra_tool, a
gateway tool) is the caller asking for a loop and still upgrades.

These drive build_async, the path the strategy registry actually takes.
They used to call GraphBuilder's own _build_* methods, which nothing
dispatched to -- so the zero-shot rule above was pinned only on a dead
method while the live strategy still upgraded on document tools alone.
"""

from types import SimpleNamespace

import pytest

from agents.graphs.builder import GraphBuilder
from agents.tooling.document_tools import DOCUMENT_TOOL_PROMPT


def _fake_document_tools() -> list[SimpleNamespace]:
    return [SimpleNamespace(name="create_document"), SimpleNamespace(name="create_spreadsheet")]


def _with_document_tools(monkeypatch, tools=_fake_document_tools) -> None:
    monkeypatch.setattr("agents.tooling.document_tools.get_document_tools", tools)


def _capture(monkeypatch, module_path: str, factory: str) -> dict:
    captured: dict = {}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(f"{module_path}.{factory}", fake_factory)
    return captured


def _tool_names(captured: dict) -> set[str]:
    return {getattr(t, "name", None) for t in captured["tools"]}


@pytest.mark.asyncio
async def test_the_react_graph_includes_document_tools_and_prompt(monkeypatch):
    _with_document_tools(monkeypatch)
    captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

    await GraphBuilder(model=object()).build_async("react", {"system_prompt": "Be helpful."})

    assert {"create_document", "create_spreadsheet"} <= _tool_names(captured)
    assert DOCUMENT_TOOL_PROMPT in captured["system_prompt"]


@pytest.mark.asyncio
async def test_the_react_graph_skips_document_tools_when_disabled(monkeypatch):
    _with_document_tools(monkeypatch, lambda: [])
    captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

    await GraphBuilder(model=object()).build_async("react", {"system_prompt": "Be helpful."})

    assert captured["tools"] == []
    assert DOCUMENT_TOOL_PROMPT not in captured["system_prompt"]


@pytest.mark.asyncio
async def test_the_react_graph_honours_the_document_tools_opt_out(monkeypatch):
    """The flag zero-shot delegation sets: no document tools, no added prompt."""
    _with_document_tools(monkeypatch)
    captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

    await GraphBuilder(model=object()).build_async(
        "react", {"system_prompt": "Be helpful.", "document_tools": False}
    )

    assert _tool_names(captured).isdisjoint({"create_document", "create_spreadsheet"})
    assert DOCUMENT_TOOL_PROMPT not in captured["system_prompt"]


@pytest.mark.asyncio
async def test_zero_shot_stays_plain_even_when_document_tools_exist(monkeypatch):
    """Document tools alone must not turn a zero-shot graph into a react agent.

    "Zero-shot" means one model call with a system prompt; a tool loop is
    what ReActAgent is for. The silent upgrade made a Flow canvas
    ZeroShotAgent emit PDFs from a prompt that only asked for a
    one-sentence summary.
    """
    _with_document_tools(monkeypatch)

    def fail_if_called(**_kwargs):
        raise AssertionError("a tool-less zero-shot must not build a react agent")

    monkeypatch.setattr("agents.graphs.strategies.react.create_agent", fail_if_called)

    class _FakeModel:
        async def ainvoke(self, messages):
            return object()

    graph = await GraphBuilder(model=_FakeModel()).build_async("zero_shot", {})

    assert graph is not None


@pytest.mark.asyncio
async def test_zero_shot_stays_plain_when_document_tools_are_disabled(monkeypatch):
    _with_document_tools(monkeypatch, lambda: [])

    def fail_if_called(**_kwargs):
        raise AssertionError("a tool-less zero-shot must not build a react agent")

    monkeypatch.setattr("agents.graphs.strategies.react.create_agent", fail_if_called)

    class _FakeModel:
        async def ainvoke(self, messages):
            return object()

    graph = await GraphBuilder(model=_FakeModel()).build_async("zero_shot", {})

    assert graph is not None


@pytest.mark.asyncio
async def test_zero_shot_still_upgrades_when_a_tool_is_explicitly_attached(monkeypatch):
    """An explicit tool is the caller asking for a loop -- but document tools
    must not ride along into it."""
    _with_document_tools(monkeypatch)
    captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

    await GraphBuilder(model=object()).build_async("zero_shot", {"mcp_tools": ["search"]})

    assert captured, "an explicitly attached tool must still upgrade to react"
    assert _tool_names(captured).isdisjoint({"create_document", "create_spreadsheet"})
    assert DOCUMENT_TOOL_PROMPT not in captured["system_prompt"]


@pytest.mark.asyncio
async def test_plan_execute_includes_document_tools(monkeypatch):
    _with_document_tools(monkeypatch)
    captured = _capture(monkeypatch, "agents.graphs.strategies.plan_execute", "create_react_agent")

    await GraphBuilder(model=object()).build_async("plan_execute", {})

    assert {"create_document", "create_spreadsheet"} <= _tool_names(captured)


@pytest.mark.asyncio
async def test_a_sub_agent_graph_includes_document_tools(monkeypatch):
    _with_document_tools(monkeypatch)
    captured = _capture(monkeypatch, "langgraph.prebuilt", "create_react_agent")
    monkeypatch.setattr(
        "langgraph_supervisor.create_supervisor",
        lambda agents, **_kwargs: SimpleNamespace(
            compile=lambda **_kw: SimpleNamespace(name="compiled")
        ),
    )

    await GraphBuilder(model=object()).build_async(
        "supervisor",
        {
            "system_prompt": "Coordinate.",
            "sub_agents": [{"name": "worker", "system_prompt": "Do the task."}],
        },
    )

    assert {"create_document", "create_spreadsheet"} <= _tool_names(captured)
