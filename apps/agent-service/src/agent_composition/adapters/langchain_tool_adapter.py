"""Convert domain tool bindings into real LangChain tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from agent_composition.domain.errors import ToolInvocationError
from agent_composition.domain.ports import ToolBinding, ToolInvocation
from agent_composition.domain.trusted_context import TrustedToolContext


class TrustedContextProvider:
    def __call__(self) -> TrustedToolContext | None:
        raise NotImplementedError


def _thaw_schema(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _thaw_schema(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_schema(item) for item in value]
    return value


def _format_output(output: Any) -> str:
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
    async def async_invoke(*args: Any, **kwargs: Any) -> str:
        if args and kwargs:
            raise ValueError("Cannot use both positional and keyword arguments")
        model_arguments = args[0] if args else kwargs
        context = context_provider() if context_provider is not None else None
        try:
            result = await binding.invoke(
                ToolInvocation(model_arguments=model_arguments, trusted_context=context)
            )
            return _format_output(result.output)
        except ToolInvocationError as exc:
            return f"Tool invocation failed: {exc.message}"

    return async_invoke


def _make_sync_stub() -> Callable[..., str]:
    def sync_func(*args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Tool created from ToolBinding only supports async invocation")

    return sync_func


class LangChainToolAdapter(StructuredTool):
    """A StructuredTool backed by a domain ToolBinding."""

    def __init__(
        self,
        binding: ToolBinding,
        context_provider: TrustedContextProvider | None = None,
    ) -> None:
        descriptor = binding.descriptor
        super().__init__(
            name=descriptor.key,
            description=descriptor.description,
            func=_make_sync_stub(),
            coroutine=_make_async_invoke(binding, context_provider),
            args_schema=_thaw_schema(descriptor.input_schema)
            or {"type": "object", "properties": {}},
        )

    def _run(self, *args: Any, config: Any = None, **kwargs: Any) -> str:
        return self.func(*args, **kwargs)

    async def _arun(self, *args: Any, config: Any = None, **kwargs: Any) -> str:
        if self.coroutine is None:
            raise NotImplementedError("Tool created from ToolBinding only supports async invocation")
        return await self.coroutine(*args, **kwargs)


def tool_binding_to_langchain_tool(
    binding: ToolBinding,
    context_provider: TrustedContextProvider | None = None,
) -> LangChainToolAdapter:
    return LangChainToolAdapter(binding=binding, context_provider=context_provider)


def tool_bindings_to_langchain_tools(
    bindings: tuple[ToolBinding, ...],
    context_provider: TrustedContextProvider | None = None,
) -> list[LangChainToolAdapter]:
    return [tool_binding_to_langchain_tool(binding, context_provider) for binding in bindings]
