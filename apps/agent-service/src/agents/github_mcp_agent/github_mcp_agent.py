"""GitHub MCP Agent - An agent that uses GitHub MCP tools for repository management."""

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
from core import get_model, settings

logger = logging.getLogger(__name__)

current_date = datetime.now().strftime("%B %d, %Y")
prompt = f"""
You are GitHubBot, a specialized assistant for GitHub repository management and development workflows.
You have access to GitHub MCP tools that allow you to interact with GitHub repositories, issues, pull requests,
and other GitHub resources. Today's date is {current_date}.

Your capabilities include:
- Repository management (create, clone, browse)
- Issue management (create, list, update, close)
- Pull request management (create, review, merge)
- Branch management (create, switch, merge)
- File operations (read, write, search)
- Commit operations (create, view history)

Guidelines:
- Always be helpful and provide clear explanations of GitHub operations
- When creating or modifying content, ensure it follows best practices
- Be cautious with destructive operations (deletes, force pushes, etc.)
- Provide context about what you're doing and why
- Use appropriate commit messages and PR descriptions
- Respect repository permissions and access controls

NOTE: You have access to GitHub MCP tools that provide direct GitHub API access.
"""

# Context variable for trusted context at invocation time.
_gh_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar(
    "_gh_trusted_context_var", default=None
)


class GitHubMCPAgent(LazyLoadingAgent):
    """GitHub MCP Agent with async initialization.

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
        """Initialize the GitHub MCP agent by loading MCP tools."""
        connections = {}

        # GitHub MCP Server connection
        if settings.GITHUB_PAT:
            try:
                github_pat = settings.GITHUB_PAT.get_secret_value()
                connections["github"] = StreamableHttpConnection(
                    transport="streamable_http",
                    url=settings.MCP_GITHUB_SERVER_URL,
                    headers={"Authorization": f"Bearer {github_pat}"},
                )
            except Exception as e:
                logger.error(f"Failed to configure GitHub connection: {e}")
        else:
            logger.warning("GITHUB_PAT not set, skipping GitHub MCP server connection")

        # Local MCP Server connection (for git/file operations)
        try:
            connections["local-mcp"] = StreamableHttpConnection(
                transport="streamable_http",
                url=settings.MCP_SERVER_URL,
            )
        except Exception as e:
            logger.error(f"Failed to configure local MCP connection: {e}")

        if not connections:
            logger.error("No MCP connections configured for GitHub Agent")
            self._mcp_tools = []
            self._graph = self._create_graph()
            self._loaded = True
            return

        try:
            # Initialize MCP client with configured connections
            self._mcp_client = MultiServerMCPClient(connections)
            logger.info(f"MCP client initialized with servers: {list(connections.keys())}")

            # Get tools from the client
            self._mcp_tools = await self._mcp_client.get_tools()
            logger.info(f"GitHub MCP agent initialized with {len(self._mcp_tools)} tools")

        except Exception as e:
            logger.error(f"Failed to initialize GitHub MCP agent: {e}")
            self._mcp_tools = []
            self._mcp_client = None

        # If a gateway is injected, also resolve tools through it.
        if self._gateway is not None:
            try:
                await self._gateway.load()
                all_descriptors = await self._gateway.describe()
                all_keys = tuple(d.key for d in all_descriptors)
                bindings = await self._gateway.resolve(all_keys)

                def _context_provider() -> TrustedToolContext | None:
                    return _gh_trusted_context_var.get()

                self._gateway_tools = tool_bindings_to_langchain_tools(
                    bindings, context_provider=_context_provider
                )
                logger.info(
                    "GitHubMCPAgent resolved %d tools via gateway", len(self._gateway_tools)
                )
            except Exception as e:
                logger.warning("GitHubMCPAgent gateway tool resolution failed: %s", e)
                self._gateway_tools = []

        # Create and store the graph
        self._graph = self._create_graph()
        self._loaded = True

    def _create_graph(self) -> CompiledStateGraph:
        """Create the GitHub MCP agent graph."""
        model = get_model(settings.DEFAULT_MODEL)

        # Prepend gateway tools so they take precedence.
        tools = list(self._gateway_tools) + self._mcp_tools

        return create_agent(
            model=model,
            tools=tools,
            name="github-mcp-agent",
            system_prompt=prompt,
        )

    async def ainvoke(
        self,
        input,
        config: RunnableConfig | None = None,
        **kwargs,
    ):
        await self.ensure_loaded()
        token = _gh_trusted_context_var.set(self._build_trusted_context(config))
        try:
            return await self._graph.ainvoke(input, config=config, **kwargs)
        finally:
            _gh_trusted_context_var.reset(token)

    async def astream(
        self,
        input,
        config: RunnableConfig | None = None,
        **kwargs,
    ):
        await self.ensure_loaded()
        token = _gh_trusted_context_var.set(self._build_trusted_context(config))
        try:
            async for event in self._graph.astream(input, config=config, **kwargs):
                yield event
        finally:
            _gh_trusted_context_var.reset(token)

    async def astream_events(
        self,
        input,
        config: RunnableConfig | None = None,
        version: str = "v2",
        **kwargs,
    ):
        await self.ensure_loaded()
        token = _gh_trusted_context_var.set(self._build_trusted_context(config))
        try:
            async for event in self._graph.astream_events(
                input,
                config=config,
                version=version,
                **kwargs,
            ):
                yield event
        finally:
            _gh_trusted_context_var.reset(token)


# Create the agent instance
github_mcp_agent = GitHubMCPAgent()
