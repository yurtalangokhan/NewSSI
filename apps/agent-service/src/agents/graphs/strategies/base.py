"""Base class for graph schema strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from langchain_core.language_models.chat_models import BaseChatModel

from agents.graphs.schemas import GraphSchemaType
from core.logger import get_logger

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
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.mcp_tools_map = mcp_tools_map or {}
        self.memory_enabled = memory_enabled
        self.checkpointer = checkpointer
        self.repository = repository

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

    def _get_model(self, model_name: str | None = None) -> BaseChatModel:
        """Get model instance, using override or default."""
        if model_name:
            from core import get_model

            return get_model(model_name)
        if self.model:
            return self.model
        from core import get_model, settings

        return get_model(settings.DEFAULT_MODEL)

    def _get_tools_for_names(
        self,
        tool_names: list[str],
        *,
        tool_configs: dict[str, Any] | None = None,
        user_id: str | None = None,
        mail_attachments: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        """Get tool instances from names using the tools map."""
        from agents.mail_tooling import maybe_wrap_mcp_tool

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

    def _get_document_tools(self) -> list[Any]:
        """Get document tools if available."""
        from agents.document_tools import get_document_tools

        return get_document_tools()

    def _apply_document_tools(self, tools: list[Any], system_prompt: str) -> tuple[list[Any], str]:
        """Apply document tools to tool list and prompt."""
        from agents.document_tools import DOCUMENT_TOOL_PROMPT

        document_tools = self._get_document_tools()
        if document_tools:
            tools = list(tools) + document_tools
            system_prompt = f"{system_prompt}\n{DOCUMENT_TOOL_PROMPT}"
        return tools, system_prompt
