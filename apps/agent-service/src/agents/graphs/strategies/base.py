"""Base class for graph schema strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from typing import TYPE_CHECKING, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from core.observability.logger import get_logger
from schemas.agent_graphs import GraphSchemaType

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.pregel import Pregel

logger = get_logger(__name__)


class GraphSchemaStrategy(ABC):
    """
    Base class for graph schema strategies.

    Each strategy knows how to validate its configuration and build its graph.
    """

    # Subclasses must set the schema type
    schema_type: GraphSchemaType

    def __init__(
        self,
        model: BaseChatModel | None = None,
        system_prompt: str = "You are a helpful AI assistant.",
        tools: list[Any] | None = None,
        mcp_tools_map: dict[str, Any] | None = None,
        memory_enabled: bool = False,
        checkpointer: Any | None = None,
        repository: Any | None = None,
        gateway_tools: list[Any] | None = None,
        depth: int = 0,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.mcp_tools_map = mcp_tools_map or {}
        self.memory_enabled = memory_enabled
        self.checkpointer = checkpointer
        # Built-in tools-service tools resolved via ToolsServiceToolGateway.
        # Unlike mcp_tools_map (external MCP servers, selected by name),
        # these are always available and must be prepended by every
        # concrete strategy via _with_gateway_tools before binding tools.
        self.gateway_tools = gateway_tools or []
        self.repository = repository
        # How many supervisor/pipeline levels deep this strategy instance
        # is nested. A sub-agent chain that loops back on itself used to
        # recurse here with no bound at all — see MAX_NESTED_SUB_AGENT_DEPTH
        # in agents.graphs.builder.
        self._depth = depth

    @abstractmethod
    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """
        Validate the configuration for this schema.

        Returns:
            Tuple of validation error messages (empty if valid).
        """
        ...

    @abstractmethod
    async def build(self, config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """
        Build the graph from configuration.

        Args:
            config: Configuration dict for the graph

        Returns:
            Compiled graph
        """
        ...

    async def _get_model(self, model_name: str | None = None) -> BaseChatModel:
        """Get model instance, using override or default.

        Resolution runs in a worker thread because it can go to the network:
        inside a running loop get_model takes its direct-lookup branch, which
        asks Ollama whether the model supports reasoning over a synchronous
        client with a three second timeout. On the loop, the first use of a
        cold model stalls every other request in the process until that
        answers. An injected model skips the lookup entirely.
        """
        if model_name:
            from infrastructure.llm import get_model

            return await asyncio.to_thread(get_model, model_name)
        if self.model:
            return self.model
        from config_manager import env

        from infrastructure.llm import get_model

        return await asyncio.to_thread(get_model, env.DEFAULT_MODEL)

    def _get_tools_for_names(
        self,
        tool_names: list[str],
        *,
        tool_configs: dict[str, Any] | None = None,
        user_id: str | None = None,
        mail_attachments: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        """Get tool instances from names using the tools map."""
        from agents.tooling.mail_tooling import maybe_wrap_mcp_tool

        tools = []
        for name in tool_names:
            if name in self.mcp_tools_map:
                tools.append(
                    maybe_wrap_mcp_tool(
                        tool_name=name,
                        tool=self.mcp_tools_map[name],
                        tool_configs=tool_configs,
                        user_id=user_id,
                        mail_attachments=mail_attachments,
                    )
                )
            else:
                logger.warning(f"Tool '{name}' not found in tools map")
        return tools

    def _with_gateway_tools(self, tools: list[Any]) -> list[Any]:
        """Prepend built-in tools-service tools resolved via the gateway.

        These are always available regardless of which ``mcp_tools`` names
        the agent's config selected, unlike ``_get_tools_for_names`` (which
        only resolves names against ``mcp_tools_map``) — so every strategy
        must add them itself right before binding its final tool list.
        """
        if not self.gateway_tools:
            return tools
        return list(self.gateway_tools) + list(tools)

    def _get_document_tools(self) -> list[Any]:
        """Get document tools if available."""
        from agents.tooling.document_tools import get_document_tools

        return get_document_tools()

    def _apply_document_tools(
        self, tools: list[Any], system_prompt: str, *, enabled: bool = True
    ) -> tuple[list[Any], str]:
        """Apply document tools to tool list and prompt.

        ``enabled`` is how zero-shot delegation says "upgrade me to a react
        loop for the tool I asked for, but do not hand the model document
        tools I never asked for" -- and do not extend my prompt with theirs.
        """
        from agents.tooling.document_tools import DOCUMENT_TOOL_PROMPT

        document_tools = self._get_document_tools() if enabled else []
        if document_tools:
            tools = list(tools) + document_tools
            system_prompt = f"{system_prompt}\n{DOCUMENT_TOOL_PROMPT}"
        return tools, system_prompt

    def _react_prompt(self, system_prompt: str, tools: list[Any]) -> Any:
        """The ``create_react_agent`` prompt for a graph with these final tools.

        A model that owns ``list_attachments`` gets the chat's attached-image manifest
        added on every call (see ``agents.tooling.attachment_manifest``); any other
        graph keeps the plain, static system message.
        """
        from agents.tooling.attachment_manifest import attachment_aware_prompt, has_attachment_tool

        if has_attachment_tool(tools):
            return attachment_aware_prompt(system_prompt)
        return SystemMessage(content=system_prompt)

    def _attachment_middleware(self, tools: list[Any]) -> list[Any]:
        """The ``create_agent`` form of ``_react_prompt``: the manifest middleware, or none."""
        from agents.graphs.middleware import AttachmentManifestMiddleware
        from agents.tooling.attachment_manifest import has_attachment_tool

        return [AttachmentManifestMiddleware()] if has_attachment_tool(tools) else []

    def _attach_clarification(self, tools: list[Any], system_prompt: str) -> tuple[list[Any], str]:
        """Offer ``ask_user``, but only to a graph that can actually pause.

        The tool works by interrupting the run, which needs somewhere to
        write the pending state; without a checkpointer there is nowhere, so
        a call would strand the model mid-turn (E13). Flow canvas graphs are
        always built with ``checkpointer=None`` and therefore never see it
        (K3, E14), and a RunFlow sub-run cannot pause at all.
        """
        from agents.clarification.prompt import ASK_USER_PROMPT
        from agents.clarification.tool import get_clarification_tools

        if not self.checkpointer:
            return tools, system_prompt
        tools = list(tools) + list(get_clarification_tools())
        return tools, f"{system_prompt}\n{ASK_USER_PROMPT}"

    def _clarification_post_model_hook(self):
        """The "call ask_user alone" guard, in ``create_react_agent`` form.

        ``create_agent`` takes the guard as ``AskUserAloneMiddleware``;
        ``create_react_agent`` has no middleware slot, so the strategies on
        that factory take the same guard as a ``post_model_hook``. Gated on
        the same checkpointer as the tool: no tool attached, no guard needed,
        so ``None`` (the factory's own default) is correct there.
        """
        from agents.clarification.middleware import ask_user_alone_post_model_hook

        return ask_user_alone_post_model_hook if self.checkpointer else None
