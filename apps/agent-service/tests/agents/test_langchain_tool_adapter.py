"""Tests for LangChainToolAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_composition import (
    ToolDescriptor,
    ToolInvocation,
    ToolResult,
)
from agent_composition.adapters.langchain_tool_adapter import (
    LangChainToolAdapter,
    TrustedContextProvider,
    _format_output,
    tool_binding_to_langchain_tool,
    tool_bindings_to_langchain_tools,
)
from agent_composition.domain.errors import ToolInvocationError


class TestFormatOutput:
    def test_format_output_with_text_list(self) -> None:
        output = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        assert _format_output(output) == "hello\nworld"

    def test_format_output_with_mixed_list(self) -> None:
        output = [
            {"type": "text", "text": "hello"},
            {"type": "image", "url": "http://example.com/img.png"},
        ]
        assert _format_output(output) == "hello\nhttp://example.com/img.png"

    def test_format_output_with_string(self) -> None:
        assert _format_output("hello") == "hello"

    def test_format_output_with_none(self) -> None:
        assert _format_output(None) == ""


class TestLangChainToolAdapter:
    @pytest.mark.asyncio
    async def test_ainvoke_calls_binding_with_trusted_context(self) -> None:
        mock_binding = MagicMock()
        mock_binding.descriptor = ToolDescriptor(
            key="test_tool",
            description="A test tool",
        )
        mock_binding.invoke = AsyncMock(return_value=ToolResult(output={"result": "success"}))

        mock_provider = MagicMock(spec=TrustedContextProvider)
        mock_provider.return_value = None

        adapter = LangChainToolAdapter(
            binding=mock_binding,
            context_provider=mock_provider,
        )

        result = await adapter.ainvoke({"query": "test"})

        assert result == "{'result': 'success'}"
        mock_binding.invoke.assert_called_once()
        call_args = mock_binding.invoke.call_args[0][0]
        assert isinstance(call_args, ToolInvocation)
        assert call_args.model_arguments == {"query": "test"}

    @pytest.mark.asyncio
    async def test_ainvoke_with_trusted_context_provider(self) -> None:
        mock_binding = MagicMock()
        mock_binding.descriptor = ToolDescriptor(
            key="search",
            description="Search tool",
        )
        mock_binding.invoke = AsyncMock(
            return_value=ToolResult(output=[{"type": "text", "text": "found"}])
        )

        mock_provider = MagicMock(spec=TrustedContextProvider)
        mock_context = MagicMock()
        mock_context.user_id = "u1"
        mock_context.tenant_id = "t1"
        mock_context.binding_references = {}
        mock_context.attachment_handles = ()
        mock_provider.return_value = mock_context

        adapter = LangChainToolAdapter(
            binding=mock_binding,
            context_provider=mock_provider,
        )

        result = await adapter.ainvoke({"query": "test"})

        assert result == "found"
        mock_provider.assert_called_once()
        call_args = mock_binding.invoke.call_args[0][0]
        assert call_args.trusted_context == mock_context

    @pytest.mark.asyncio
    async def test_ainvoke_handles_tool_invocation_error(self) -> None:
        mock_binding = MagicMock()
        mock_binding.descriptor = ToolDescriptor(
            key="failing_tool",
            description="A tool that fails",
        )
        mock_binding.invoke = AsyncMock(
            side_effect=ToolInvocationError(
                message="Tool call failed",
                details={"code": -32600},
            )
        )

        adapter = tool_binding_to_langchain_tool(mock_binding)

        result = await adapter.ainvoke({"input": "test"})

        assert "Tool invocation failed" in result
        assert "Tool call failed" in result

    def test_sync_run_raises_not_implemented(self) -> None:
        mock_binding = MagicMock()
        mock_binding.descriptor = ToolDescriptor(
            key="async_tool",
            description="An async-only tool",
        )

        adapter = LangChainToolAdapter(mock_binding)

        with pytest.raises(NotImplementedError) as exc_info:
            adapter._run("test")
        assert "only supports async" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_arun_delegates_to_ainvoke(self) -> None:
        mock_binding = MagicMock()
        mock_binding.descriptor = ToolDescriptor(
            key="delegation_tool",
            description="A tool for _arun testing",
        )
        mock_binding.invoke = AsyncMock(return_value=ToolResult(output="delegated"))

        adapter = LangChainToolAdapter(mock_binding)

        result = await adapter._arun("test_input")

        assert result == "delegated"
        mock_binding.invoke.assert_called_once()


class TestFactoryFunctions:
    @pytest.mark.asyncio
    async def test_tool_binding_to_langchain_tool(self) -> None:
        mock_binding = MagicMock()
        mock_binding.descriptor = ToolDescriptor(
            key="factory_tool",
            description="Factory test tool",
        )
        mock_binding.invoke = AsyncMock(return_value=ToolResult(output="factory_result"))

        tool = tool_binding_to_langchain_tool(mock_binding)

        assert hasattr(tool, "name")
        assert tool.name == "factory_tool"
        assert tool.description == "Factory test tool"

    @pytest.mark.asyncio
    async def test_tool_bindings_to_langchain_tools(self) -> None:
        bindings = tuple(
            MagicMock(
                descriptor=ToolDescriptor(
                    key=f"tool_{i}",
                    description=f"Tool {i}",
                ),
                invoke=AsyncMock(return_value=ToolResult(output=f"result_{i}")),
            )
            for i in range(3)
        )

        tools = tool_bindings_to_langchain_tools(bindings)

        assert len(tools) == 3
        assert all(hasattr(t, "name") for t in tools)
        assert [t.name for t in tools] == ["tool_0", "tool_1", "tool_2"]
