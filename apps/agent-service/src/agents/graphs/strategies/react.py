"""ReAct graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies.base import GraphSchemaStrategy

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class ReActGraphStrategy(GraphSchemaStrategy):
    """Strategy for ReAct agent with tools."""

    schema_type = GraphSchemaType.REACT

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """ReAct has no required fields (system prompt has default)."""
        return ()  # All fields have defaults

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build ReAct agent graph."""
        from agents.mail_tooling import append_email_tool_policy

        tool_names = config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            config.get("system_prompt", self.system_prompt),
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
            name="react-agent",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=self.checkpointer,
        )

        return agent
