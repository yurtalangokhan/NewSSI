"""ReAct graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent

from agents.clarification.middleware import AskUserAloneMiddleware
from agents.graphs.middleware import DeadEndTurnRetryMiddleware
from agents.graphs.strategies.base import GraphSchemaStrategy
from schemas.agent_graphs import GraphSchemaType

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class ReActGraphStrategy(GraphSchemaStrategy):
    """Strategy for ReAct agent with tools."""

    schema_type = GraphSchemaType.REACT

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:  # noqa: ARG002
        """ReAct has no required fields (system prompt has default)."""
        return ()  # All fields have defaults

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build ReAct agent graph."""
        from agents.tooling.mail_tooling import append_email_tool_policy

        tool_names = config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            config.get("system_prompt", self.system_prompt),
            tool_names,
            mail_attachments=config.get("mail_attachments"),
        )
        model = await self._get_model(config.get("model"))

        tools = self._get_tools_for_names(
            tool_names,
            tool_configs=config.get("mcp_tool_configs") or {},
            user_id=config.get("user_id"),
            mail_attachments=config.get("mail_attachments"),
        )
        extra_tools = config.get("extra_tools", []) or []
        tools.extend(extra_tools)

        tools, system_prompt = self._apply_document_tools(
            tools, system_prompt, enabled=config.get("document_tools", True)
        )
        tools = self._with_gateway_tools(tools)
        tools, system_prompt = self._attach_clarification(tools, system_prompt)

        # create_agent, not langgraph.prebuilt.create_react_agent: the
        # latter is deprecated and, more to the point here, has no
        # middleware slot. DeadEndTurnRetryMiddleware needs to wrap the
        # model call to retry a turn that came back with neither content
        # nor tool calls -- a post_model_hook can rewrite that turn's
        # output but cannot ask the model again.
        agent = create_agent(
            model=model,
            tools=tools,
            name="react-agent",
            system_prompt=system_prompt,
            checkpointer=self.checkpointer,
            middleware=[
                *self._attachment_middleware(tools),
                DeadEndTurnRetryMiddleware(),
                AskUserAloneMiddleware(),
            ],
        )

        return agent
