"""Command Agent - executes deterministic commands via MCP."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import datetime

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from langgraph.graph.state import CompiledStateGraph

from agent_composition.adapters.langchain_tool_adapter import (
    tool_bindings_to_langchain_tools,
)
from agent_composition.domain.ports import ToolGateway
from agent_composition.domain.trusted_context import TrustedToolContext
from agents.lazy_agent import LazyLoadingAgent
from core import settings
from core.llm import get_model_from_config

logger = logging.getLogger(__name__)

current_date = datetime.now().strftime("%B %d, %Y")
SYSTEM_PROMPT = f"""You are a Command execution agent.
Your primary role is to execute deterministic commands using the provided tools.
You have access to shell execution, Docker management, and file operations.
Today's date is {current_date}.

Security Guidelines:
- Only execute commands that are explicitly requested.
- If Sandbox Mode is enabled (default), dangerous commands (rm -rf /, etc.) are blocked by the tool.
- Respect the allowed commands list provided in your configuration.
"""

# Context variable for trusted context at invocation time.
_cmd_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar(
    "_cmd_trusted_context_var", default=None
)


class CommandAgent(LazyLoadingAgent):
    """Command Agent with async initialization for MCP tools.

    Supports optional ToolsServiceToolGateway injection for trusted-context tool path.
    """

    def __init__(self, gateway: ToolGateway | None = None) -> None:
        super().__init__()
        self._gateway = gateway
        self._gateway_tools: list[BaseTool] = []
        self._mcp_tools: list[BaseTool] = []
        self._mcp_client: MultiServerMCPClient | None = None

    def _build_trusted_context(self, config: RunnableConfig | None) -> TrustedToolContext | None:
        """Build TrustedToolContext from LangGraph config for gateway tool invocation."""
        configurable = (config or {}).get("configurable", {})
        user_id = configurable.get("user_id")
        tenant_id = configurable.get("tenant_id")
        binding_references: dict = configurable.get("binding_references") or {}
        project_id = configurable.get("project_id")
        request_id = configurable.get("request_id")

        if not any([user_id, tenant_id, binding_references, project_id]):
            return None

        from agent_composition.domain.trusted_context import build_trusted_context

        return build_trusted_context(
            user_id=user_id,
            tenant_id=tenant_id,
            binding_references=binding_references,
            project_id=project_id,
            request_id=request_id,
        )

    async def load(self) -> None:
        """Initialize the agent by loading MCP tools."""
        try:
            # MCP connection details
            mcp_url = settings.MCP_SERVER_URL

            connections = {
                "command-server": StreamableHttpConnection(
                    transport="streamable_http",
                    url=mcp_url,
                )
            }

            self._mcp_client = MultiServerMCPClient(connections)
            logger.info(f"Connecting to MCP server at {mcp_url}")

            # Get tools
            self._mcp_tools = await self._mcp_client.get_tools()
            logger.info(f"Command agent loaded with {len(self._mcp_tools)} tools")

        except Exception as e:
            logger.error(f"Failed to initialize Command agent: {e}")
            self._mcp_tools = []

        # If a gateway is injected, also resolve tools through it.
        if self._gateway is not None:
            try:
                await self._gateway.load()
                all_descriptors = await self._gateway.describe()
                all_keys = tuple(d.key for d in all_descriptors)
                bindings = await self._gateway.resolve(all_keys)

                def _context_provider() -> TrustedToolContext | None:
                    return _cmd_trusted_context_var.get()

                self._gateway_tools = tool_bindings_to_langchain_tools(
                    bindings, context_provider=_context_provider
                )
                logger.info("CommandAgent resolved %d tools via gateway", len(self._gateway_tools))
            except Exception as e:
                logger.warning("CommandAgent gateway tool resolution failed: %s", e)
                self._gateway_tools = []

        self._graph = self._create_graph()
        self._loaded = True

    def _create_graph(self, configurable: dict | None = None) -> CompiledStateGraph:
        model = get_model_from_config(configurable or {}, settings.DEFAULT_MODEL)

        # Prepend gateway tools so they take precedence.
        tools = list(self._gateway_tools) + self._mcp_tools

        return create_agent(
            model=model,
            tools=tools,
            name="command-agent",
            system_prompt=SYSTEM_PROMPT,
        )

    def _get_runtime_graph(self, config: RunnableConfig | None) -> CompiledStateGraph:
        configurable = (config or {}).get("configurable", {})
        if any(k in configurable for k in ("model", "llm_instance")):
            return self._create_graph(configurable)
        return self._graph

    async def ainvoke(
        self,
        input,
        config: RunnableConfig | None = None,
        **kwargs,
    ):
        await self.ensure_loaded()
        token = _cmd_trusted_context_var.set(self._build_trusted_context(config))
        try:
            graph = self._get_runtime_graph(config)
            return await graph.ainvoke(input, config=config, **kwargs)
        finally:
            _cmd_trusted_context_var.reset(token)

    async def astream(
        self,
        input,
        config: RunnableConfig | None = None,
        **kwargs,
    ):
        await self.ensure_loaded()
        token = _cmd_trusted_context_var.set(self._build_trusted_context(config))
        try:
            graph = self._get_runtime_graph(config)
            async for event in graph.astream(input, config=config, **kwargs):
                yield event
        finally:
            _cmd_trusted_context_var.reset(token)

    async def astream_events(
        self,
        input,
        config: RunnableConfig | None = None,
        version: str = "v2",
        **kwargs,
    ):
        await self.ensure_loaded()
        token = _cmd_trusted_context_var.set(self._build_trusted_context(config))
        try:
            graph = self._get_runtime_graph(config)
            async for event in graph.astream_events(
                input,
                config=config,
                version=version,
                **kwargs,
            ):
                yield event
        finally:
            _cmd_trusted_context_var.reset(token)


command_agent = CommandAgent()
