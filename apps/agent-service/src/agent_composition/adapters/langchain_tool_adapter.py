"""Convert domain tool bindings into real LangChain tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from agent_composition.domain.errors import ToolInvocationError
from agent_composition.domain.ports import (
    ToolArtifactPolicy,
    ToolBinding,
    ToolInvocation,
    ToolResult,
    thaw_value,
)
from agent_composition.domain.trusted_context import TrustedToolContext
from core.observability.logger import get_logger

logger = get_logger(__name__)


class TrustedContextProvider:
    def __call__(self) -> TrustedToolContext | None:
        raise NotImplementedError


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


ToolOutput = tuple[str, dict[str, Any] | None]


async def _artifact_for(
    policy: ToolArtifactPolicy | None,
    tool_name: str,
    result: ToolResult,
) -> dict[str, Any] | None:
    """The policy's artifact; a failing policy costs the artifact, never the call."""
    if policy is None:
        return None
    try:
        artifact = await policy.artifact_for(tool_name, result)
    except Exception:
        logger.warning("Artifact policy failed for tool '%s'", tool_name, exc_info=True)
        return None
    return dict(artifact) if artifact else None


def _make_async_invoke(
    binding: ToolBinding,
    context_provider: TrustedContextProvider | None,
    artifact_policy: ToolArtifactPolicy | None,
) -> Callable[..., Any]:
    async def async_invoke(*args: Any, **kwargs: Any) -> ToolOutput:
        if args and kwargs:
            raise ValueError("Cannot use both positional and keyword arguments")
        model_arguments = args[0] if args else kwargs
        context = context_provider() if context_provider is not None else None
        try:
            result = await binding.invoke(ToolInvocation(model_arguments=model_arguments, trusted_context=context))
        except ToolInvocationError as exc:
            return f"Tool invocation failed: {exc.message}", None
        artifact = await _artifact_for(artifact_policy, binding.descriptor.key, result)
        return _format_output(result.output), artifact

    return async_invoke


def _make_sync_stub() -> Callable[..., str]:
    def sync_func(*args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("Tool created from ToolBinding only supports async invocation")

    return sync_func


class LangChainToolAdapter(StructuredTool):
    """A StructuredTool backed by a domain ToolBinding.

    Results use LangChain's ``content_and_artifact`` format: the model reads the
    text, and ``artifact_policy`` may attach a platform-only artifact (for
    example a knowledge evidence reference) to the ToolMessage.
    """

    def __init__(
        self,
        binding: ToolBinding,
        context_provider: TrustedContextProvider | None = None,
        artifact_policy: ToolArtifactPolicy | None = None,
    ) -> None:
        descriptor = binding.descriptor
        super().__init__(
            name=descriptor.key,
            description=descriptor.description,
            func=_make_sync_stub(),
            coroutine=_make_async_invoke(binding, context_provider, artifact_policy),
            args_schema=thaw_value(descriptor.input_schema) or {"type": "object", "properties": {}},
            response_format="content_and_artifact",
        )

    def _run(self, *args: Any, config: Any = None, **kwargs: Any) -> str:
        del config  # accepted so a stray ``config`` never becomes a tool argument
        return self.func(*args, **kwargs)

    async def _arun(self, *args: Any, config: Any = None, **kwargs: Any) -> ToolOutput:
        del config  # accepted so a stray ``config`` never becomes a tool argument
        if self.coroutine is None:
            raise NotImplementedError("Tool created from ToolBinding only supports async invocation")
        return await self.coroutine(*args, **kwargs)


def tool_binding_to_langchain_tool(
    binding: ToolBinding,
    context_provider: TrustedContextProvider | None = None,
    artifact_policy: ToolArtifactPolicy | None = None,
) -> LangChainToolAdapter:
    return LangChainToolAdapter(binding=binding, context_provider=context_provider, artifact_policy=artifact_policy)


def tool_bindings_to_langchain_tools(
    bindings: tuple[ToolBinding, ...],
    context_provider: TrustedContextProvider | None = None,
    artifact_policy: ToolArtifactPolicy | None = None,
) -> list[LangChainToolAdapter]:
    return [tool_binding_to_langchain_tool(binding, context_provider, artifact_policy) for binding in bindings]
