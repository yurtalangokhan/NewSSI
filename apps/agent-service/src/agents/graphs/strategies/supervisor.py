"""Supervisor graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies.base import GraphSchemaStrategy
from core.logger import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.pregel import Pregel

logger = get_logger(__name__)


class SupervisorGraphStrategy(GraphSchemaStrategy):
    """Strategy for supervisor - multi-agent coordination with delegation."""

    schema_type = GraphSchemaType.SUPERVISOR

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """
        Validate supervisor configuration.

        Supervisor requires sub_agents to be non-empty if provided.
        """
        errors: list[str] = []

        sub_agents = config.get("sub_agents", [])
        if sub_agents is not None and not isinstance(sub_agents, list):
            errors.append("supervisor: sub_agents must be a list")
        elif sub_agents is not None and len(sub_agents) == 0:
            errors.append("supervisor: sub_agents list cannot be empty")

        # Validate each sub-agent has required fields
        if sub_agents:
            for i, agent in enumerate(sub_agents):
                if not isinstance(agent, dict):
                    errors.append(f"supervisor: sub_agent[{i}] must be a dict")
                    continue
                if "name" not in agent:
                    errors.append(f"supervisor: sub_agent[{i}] missing required 'name' field")

        return tuple(errors)

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build supervisor graph with sub-agents."""
        from langgraph_supervisor import create_supervisor

        supervisor_prompt = config.get("supervisor_prompt", "You are a team supervisor.")
        model = self._get_model(config.get("model"))

        sub_agents_config = config.get("sub_agents", [])
        if not sub_agents_config:
            logger.warning("No sub-agents configured for supervisor, using fallback")
            fallback_agent = create_react_agent(
                model=model,
                tools=[],
                name="fallback",
                prompt="You are a helpful assistant.",
            )
            workflow = create_supervisor(
                [fallback_agent],
                model=model,
                prompt="No sub-agents configured.",
                add_handoff_back_messages=True,
                output_mode="full_history",
            )
            return workflow.compile(checkpointer=self.checkpointer)

        agents_list = []
        agent_descriptions = []

        for sub_agent_cfg in sub_agents_config:
            if not isinstance(sub_agent_cfg, dict):
                continue

            name = sub_agent_cfg.get("name", "agent")
            sa_system_prompt = sub_agent_cfg.get("system_prompt", "You are a helpful agent.")
            tool_names = sub_agent_cfg.get("mcp_tools", [])
            if config.get("user_id") and not sub_agent_cfg.get("user_id"):
                sub_agent_cfg["user_id"] = config["user_id"]
            if config.get("mail_attachments") and not sub_agent_cfg.get("mail_attachments"):
                sub_agent_cfg["mail_attachments"] = config["mail_attachments"]
            agent = self._build_sub_agent_graph(sub_agent_cfg)

            agents_list.append(agent)
            tool_list = ", ".join(tool_names) if tool_names else "no tools"
            agent_descriptions.append(f"- {name}: {sa_system_prompt[:60]}... (tools: {tool_list})")

        enhanced_supervisor_prompt = (
            f"{supervisor_prompt}\n\nAvailable agents:\n"
            + "\n".join(agent_descriptions)
            + "\n\nDelegate tasks to the appropriate agent(s)."
        )

        workflow = create_supervisor(
            agents_list,
            model=model,
            prompt=enhanced_supervisor_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile(checkpointer=self.checkpointer, name=config.get("name"))

    def _build_sub_agent_graph(self, agent_config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build a sub-agent graph, preserving nested manager schemas when configured."""
        from langgraph.prebuilt import create_react_agent

        from agents.graphs.schemas import GraphSchemaType
        from agents.mail_tooling import append_email_tool_policy

        schema_value = agent_config.get("graph_schema")
        try:
            schema_type = GraphSchemaType(schema_value) if schema_value else GraphSchemaType.REACT
        except ValueError:
            schema_type = GraphSchemaType.REACT

        # Recursively handle nested supervisor/pipeline
        if schema_type in (GraphSchemaType.SUPERVISOR, GraphSchemaType.PIPELINE):
            from agents.graphs.strategies.pipeline import PipelineGraphStrategy
            from agents.graphs.strategies.supervisor import SupervisorGraphStrategy

            nested_strategy_class = (
                SupervisorGraphStrategy
                if schema_type == GraphSchemaType.SUPERVISOR
                else PipelineGraphStrategy
            )
            nested_strategy = nested_strategy_class(
                model=self._get_model(agent_config.get("model")),
                system_prompt=agent_config.get("system_prompt", self.system_prompt),
                tools=self.tools,
                mcp_tools_map=self.mcp_tools_map,
                memory_enabled=self.memory_enabled,
                checkpointer=self.checkpointer,
                repository=self.repository,
            )
            return nested_strategy.build(agent_config)

        name = agent_config.get("name", "agent")
        tool_names = agent_config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            agent_config.get("system_prompt", "You are a helpful agent."),
            tool_names,
            mail_attachments=agent_config.get("mail_attachments"),
        )
        agent_model = self._get_model(agent_config.get("model"))
        agent_tools = self._get_tools_for_names(
            tool_names,
            tool_configs=agent_config.get("mcp_tool_configs") or {},
            user_id=agent_config.get("user_id"),
            mail_attachments=agent_config.get("mail_attachments"),
        )

        agent_tools, system_prompt = self._apply_document_tools(agent_tools, system_prompt)

        return create_react_agent(
            model=agent_model,
            tools=agent_tools,
            name=name,
            prompt=SystemMessage(content=system_prompt),
        )
