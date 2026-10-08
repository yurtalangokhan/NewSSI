"""The ask_user tool has to reach the graph production actually builds.

``GraphBuilder.build``/``build_async`` dispatch through the strategy
registry. The clarification wiring -- the ``ask_user`` tool, the prompt that
explains it, and the guard that stops the model calling it alongside other
tools -- lived only on ``GraphBuilder``'s own ``_build_*`` methods, which
nothing outside the tests calls. Every test that covered it exercised those
methods, so the suite was green while no graph a user ever talked to
offered the tool at all.

Same for ``DeadEndTurnRetryMiddleware``, which exists because a reasoning
model can end its turn with neither content nor tool calls and hand the
client a blank response: it was installed on the dead react build, and the
live one ran the deprecated ``create_react_agent`` with no middleware at
all.

These pin the wiring on the path ``build_async`` really takes, per schema.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.graphs.builder import GraphBuilder


def _capture(monkeypatch, module_path: str, factory: str) -> dict:
    captured: dict = {}

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(f"{module_path}.{factory}", fake_factory)
    return captured


def _tool_names(captured: dict) -> set[str]:
    return {getattr(tool, "name", None) for tool in captured.get("tools", [])}


class TestReActStrategy:
    @pytest.mark.asyncio
    async def test_a_persistent_chat_agent_is_offered_the_tool(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

        builder = GraphBuilder(model=object(), checkpointer=object())
        await builder.build_async("react", {"system_prompt": "Be helpful."})

        assert "ask_user" in _tool_names(captured)
        assert "ask_user" in captured["system_prompt"]
        assert "Be helpful." in captured["system_prompt"]

    @pytest.mark.asyncio
    async def test_without_persistence_the_tool_is_not_offered(self, monkeypatch) -> None:
        """A tool that cannot pause is worse than no tool at all."""
        captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

        builder = GraphBuilder(model=object(), checkpointer=None)
        await builder.build_async("react", {"system_prompt": "Be helpful."})

        assert "ask_user" not in _tool_names(captured)
        assert "ask_user" not in captured["system_prompt"]
        assert "Be helpful." in captured["system_prompt"]

    @pytest.mark.asyncio
    async def test_the_turn_level_guards_are_installed(self, monkeypatch) -> None:
        from agents.clarification.middleware import AskUserAloneMiddleware
        from agents.graphs.middleware import DeadEndTurnRetryMiddleware

        captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

        builder = GraphBuilder(model=object(), checkpointer=object())
        await builder.build_async("react", {"system_prompt": "Be helpful."})

        installed = {type(m) for m in captured.get("middleware", [])}
        assert DeadEndTurnRetryMiddleware in installed
        assert AskUserAloneMiddleware in installed

    @pytest.mark.asyncio
    async def test_zero_shot_with_tools_inherits_the_same_wiring(self, monkeypatch) -> None:
        captured = _capture(monkeypatch, "agents.graphs.strategies.react", "create_agent")

        builder = GraphBuilder(
            model=object(),
            checkpointer=object(),
            gateway_tools=[SimpleNamespace(name="builtin_search")],
        )
        await builder.build_async("zero_shot", {"system_prompt": "Be helpful."})

        assert "ask_user" in _tool_names(captured)


class TestCreateReactAgentStrategies:
    """Strategies on ``create_react_agent`` take the guard as a post_model_hook.

    That factory has no middleware slot, which is exactly why the hook form
    of the guard exists.
    """

    @pytest.mark.asyncio
    async def test_plan_execute_gets_the_tool_and_the_hook(self, monkeypatch) -> None:
        from agents.clarification.middleware import ask_user_alone_post_model_hook

        captured = _capture(
            monkeypatch, "agents.graphs.strategies.plan_execute", "create_react_agent"
        )

        builder = GraphBuilder(model=object(), checkpointer=object())
        await builder.build_async("plan_execute", {"system_prompt": "Be helpful."})

        assert "ask_user" in _tool_names(captured)
        assert captured.get("post_model_hook") is ask_user_alone_post_model_hook

    @pytest.mark.asyncio
    async def test_plan_execute_without_persistence_gets_neither(self, monkeypatch) -> None:
        captured = _capture(
            monkeypatch, "agents.graphs.strategies.plan_execute", "create_react_agent"
        )

        builder = GraphBuilder(model=object(), checkpointer=None)
        await builder.build_async("plan_execute", {"system_prompt": "Be helpful."})

        assert "ask_user" not in _tool_names(captured)
        assert captured.get("post_model_hook") is None

    @pytest.mark.asyncio
    async def test_a_supervisor_sub_agent_gets_the_tool_and_the_hook(self, monkeypatch) -> None:
        from agents.clarification.middleware import ask_user_alone_post_model_hook

        captured = _capture(monkeypatch, "langgraph.prebuilt", "create_react_agent")
        monkeypatch.setattr(
            "langgraph_supervisor.create_supervisor",
            lambda agents, **_kwargs: SimpleNamespace(
                compile=lambda **_kw: SimpleNamespace(name="compiled")
            ),
        )

        builder = GraphBuilder(model=object(), checkpointer=object())
        await builder.build_async(
            "supervisor",
            {
                "system_prompt": "Coordinate.",
                "sub_agents": [{"name": "worker", "system_prompt": "Work."}],
            },
        )

        assert "ask_user" in _tool_names(captured)
        assert captured.get("post_model_hook") is ask_user_alone_post_model_hook

    @pytest.mark.asyncio
    async def test_a_pipeline_sub_agent_gets_the_tool_and_the_hook(self, monkeypatch) -> None:
        from agents.clarification.middleware import ask_user_alone_post_model_hook

        captured = _capture(monkeypatch, "langgraph.prebuilt", "create_react_agent")
        monkeypatch.setattr(
            "langgraph_supervisor.create_supervisor",
            lambda agents, **_kwargs: SimpleNamespace(
                compile=lambda **_kw: SimpleNamespace(name="compiled")
            ),
        )

        builder = GraphBuilder(model=object(), checkpointer=object())
        await builder.build_async(
            "pipeline",
            {
                "pipeline_prompt": "Run in order.",
                "stages": [{"name": "step-one", "system_prompt": "Do."}],
            },
        )

        assert "ask_user" in _tool_names(captured)
        assert captured.get("post_model_hook") is ask_user_alone_post_model_hook
