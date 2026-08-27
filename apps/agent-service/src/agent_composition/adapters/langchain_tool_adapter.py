"""LangChain tool adapter for ToolBinding.

Allows ToolsServiceToolGateway to be used in existing LangGraph infrastructure
by wrapping ToolBinding instances as LangChain-compatible tool objects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_composition.domain.errors import ToolInvocationError
from agent_composition.domain.ports import ToolBinding, ToolInvocation
from agent_composition.domain.trusted_context import TrustedToolContext


class TrustedContextProvider:
    """Callable that returns TrustedToolContext for the current request.

    Implementations can extract context from LangGraph config, thread-local storage,
    or any other request-scoped source.
    """

    def __call__(self) -> TrustedToolContext | None:
        raise NotImplementedError


def _format_output(output: Any) -> str:
    """Format ToolResult output for LangChain tool return."""
    if isinstance(output, (list, tuple)):
        text_parts = []
        for item in output:
            if isinstance(item, dict) or hasattr(item, "get"):
                item_type = item.get("type") if hasattr(item, "get") else None
                if item_type == "text":
                    text_parts.append(item.get("text", ""))
                elif item_type == "image":
                    text_parts.append(item.get("url", ""))
                else:
                    text_parts.append(str(dict(item)))
            else:
                text_parts.append(str(item))
        return "\n".join(text_parts)
    return str(output) if output is not None else ""


def _make_async_invoke(
    binding: ToolBinding,
    context_provider: TrustedContextProvider | None,
) -> Callable[..., Any]:
    """Create an async function that wraps ToolBinding.invoke()."""

    async def async_invoke(*args: Any, **kwargs: Any) -> str:
        if args and kwargs:
            raise ValueError("Cannot use both positional and keyword arguments")
        model_arguments = args[0] if args else kwargs

        context = None
        if context_provider is not None:
            context = context_provider()

        invocation = ToolInvocation(
            model_arguments=model_arguments,
            trusted_context=context,
        )

        try:
            result = await binding.invoke(invocation)
            return _format_output(result.output)
        except ToolInvocationError as exc:
            return f"Tool invocation failed: {exc.message}"

    return async_invoke


def _make_sync_stub() -> Callable[..., str]:
    """Create a sync stub that raises NotImplementedError."""

    def sync_func(*args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Tool created from ToolBinding only supports async invocation")

    return sync_func


class LangChainToolAdapter:
    """Wraps a ToolBinding as a LangChain-compatible tool for use in LangGraph.

    This adapter allows ToolsServiceToolGateway (which uses the ToolBinding port)
    to be used in existing LangGraph agents that expect LangChain Tool objects.

    The TrustedToolContext is obtained from the context_provider at invocation time,
    allowing server-side identity and bindings to be injected without exposing them
    to the LLM.
    """

    def __init__(
        self,
        binding: ToolBinding,
        context_provider: TrustedContextProvider | None = None,
    ) -> None:
        self.binding = binding
        self.context_provider = context_provider
        self._async_invoke = _make_async_invoke(binding, context_provider)
        self._sync_func = _make_sync_stub()
        descriptor = binding.descriptor
        self.name = descriptor.key
        self.description = descriptor.description

    def invoke(self, input: Any, config: Any = None) -> str:
        raise NotImplementedError("Tool created from ToolBinding only supports async invocation")

    async def ainvoke(self, input: Any, config: Any = None) -> str:
        return await self._async_invoke(input)

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Tool created from ToolBinding only supports async invocation")

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await self._async_invoke(*args, **kwargs)

    @property
    def args_schema(self) -> type:
        return dict


def tool_binding_to_langchain_tool(
    binding: ToolBinding,
    context_provider: TrustedContextProvider | None = None,
) -> LangChainToolAdapter:
    """Convert a ToolBinding to a LangChain-compatible tool."""
    return LangChainToolAdapter(binding=binding, context_provider=context_provider)


def tool_bindings_to_langchain_tools(
    bindings: tuple[ToolBinding, ...],
    context_provider: TrustedContextProvider | None = None,
) -> list[LangChainToolAdapter]:
    """Convert a sequence of ToolBindings to LangChain tools."""
    return [tool_binding_to_langchain_tool(binding, context_provider) for binding in bindings]
