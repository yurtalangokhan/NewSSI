"""Plan-execute graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies.base import GraphSchemaStrategy

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class PlanExecuteGraphStrategy(GraphSchemaStrategy):
    """Strategy for Plan & Execute - plan first, then execute."""

    schema_type = GraphSchemaType.PLAN_EXECUTE

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """PlanExecute has no required fields (system prompt has default)."""
        return ()  # All fields have defaults

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build Plan & Execute graph."""
        from agents.mail_tooling import append_email_tool_policy

        tool_names = config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            config.get(
                "system_prompt",
                "First create a detailed plan, then execute each step methodically.",
            ),
            tool_names,
            mail_attachments=config.get("mail_attachments"),
        )
        model = self._get_model(config.get("model"))

        tools = self._get_tools_for_names(
            tool_names,
            tool_configs=config.get("mcp_tool_configs") or {},
            user_id=config.get("user_id"),
            mail_attachments=config.get("mail_attachments"),
        )
        extra_tools = config.get("extra_tools", []) or []
        tools.extend(extra_tools)

        tools, system_prompt = self._apply_document_tools(tools, system_prompt)

        agent = create_react_agent(
            model=model,
            tools=tools,
            name="plan-execute",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=self.checkpointer,
        )

        return agent
