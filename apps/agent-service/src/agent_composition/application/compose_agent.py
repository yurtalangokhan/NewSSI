"""Agent composition facade and builder.

``AgentFactory`` is the asynchronous application facade for constructing a
persisted dynamic agent. It validates the definition and asks ``AgentComposer``
to assemble an unloaded ``ComposedAgent`` runtime, then returns the loaded
runtime.

``AgentComposer`` applies builder semantics: it wraps an already-built compiled
LangGraph graph (produced by the strategy registry in ASC-3) into a
``ComposedAgent`` (ASC-4) that owns the runtime resources. The composer never
opens network, model, store, or graph resources itself; the compiled graph is
supplied by the caller (typically after the strategy registry has built it).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agent_composition.adapters.langgraph.executable_agent import LangGraphExecutableAgent
from agent_composition.domain.definitions import RuntimePolicyConfig
from agent_composition.runtime import ComposedAgent


class AgentComposer:
    """Builder that assembles a ``ComposedAgent`` runtime from a built graph.

    The composer's responsibility is to wrap a compiled LangGraph graph in the
    runtime contract (``ComposedAgent``) that owns its lifecycle. Graph building
    (which opens model/tool/store resources and resolves nested definitions via
    the strategy registry) is performed by the caller before ``assemble`` is
    invoked.
    """

    @staticmethod
    def assemble(
        *,
        graph: CompiledStateGraph | Pregel,
        runtime_policy_config: RuntimePolicyConfig | None = None,
        checkpointer: Any | None = None,
    ) -> ComposedAgent:
        """Assemble an (unloaded) ``ComposedAgent`` around ``graph``."""
        executable = LangGraphExecutableAgent(graph)
        return ComposedAgent(
            executable_agent=executable,
            runtime_policy_config=runtime_policy_config or RuntimePolicyConfig(),
            checkpointer=checkpointer,
        )


class AgentFactory:
    """Asynchronous facade for constructing persisted dynamic agents.

    This is the canonical application entrypoint for building a new executable
    dynamic agent. It validates the definition, asks ``AgentComposer`` to
    assemble the runtime, and returns the loaded agent. The returned object is a
    ``DynamicAgent`` (the backward-compatible facade) whose construction is
    routed through ``AgentComposer`` and ``ComposedAgent``.
    """

    @classmethod
    async def create(
        cls,
        definition_config: dict[str, Any],
        *,
        gateway: Any | None = None,
        checkpointer: Any | None = None,
        repository: Any | None = None,
    ) -> Any:
        """Create and load a dynamic agent from a definition config dict.

        Args:
            definition_config: Flat ORM ``to_config()`` dict for the agent.
            gateway: Optional ``ToolGateway`` (a default is built when omitted).
            checkpointer: Optional LangGraph checkpointer for state persistence.
            repository: Optional definition repository for nested composition.

        Returns:
            A loaded ``DynamicAgent`` runtime.
        """
        from agents.dynamic_agent import DynamicAgent

        if gateway is None:
            agent = DynamicAgent(agent_config=definition_config)
        else:
            agent = DynamicAgent(agent_config=definition_config, gateway=gateway)
        if checkpointer is not None:
            agent._checkpointer = checkpointer
        await agent.load()
        return agent
