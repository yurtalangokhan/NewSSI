from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from agent_composition.adapters import tools_service_gateway as gateway_module
from agent_composition.adapters.tools_service_gateway import ToolsServiceToolGateway
from agent_composition.domain.ports import ToolInvocation
from agent_composition.domain.trusted_context import build_trusted_context


class _Result:
    def __init__(self, **values):
        self.__dict__.update(values)


class _Tool:
    name = "connector_read"
    description = "Read from an assigned connector"
    inputSchema = {
        "type": "object",
        "properties": {
            "datasource_id": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["datasource_id"],
    }


@pytest.mark.asyncio
async def test_open_mcp_session_initializes_before_yield(monkeypatch) -> None:
    events: list[str] = []
    read = object()
    write = object()

    @asynccontextmanager
    async def fake_transport(url: str, headers: dict[str, str]):
        events.append("transport_open")
        yield read, write, lambda: "session-1"
        events.append("transport_close")

    class FakeClientSession:
        def __init__(self, received_read, received_write):
            assert (received_read, received_write) == (read, write)

        async def __aenter__(self):
            events.append("session_open")
            return self

        async def __aexit__(self, *args):
            events.append("session_close")

        async def initialize(self):
            events.append("initialize")

    monkeypatch.setattr(gateway_module, "streamablehttp_client", fake_transport)
    monkeypatch.setattr(gateway_module, "ClientSession", FakeClientSession)

    async with gateway_module._open_mcp_session(
        "http://tools-service:8003/mcp", {"x-internal-token": "token"}
    ):
        events.append("yield")

    assert events == [
        "transport_open",
        "session_open",
        "initialize",
        "yield",
        "session_close",
        "transport_close",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service_url",
    ["http://tools-service:8003", "http://kong:8000/internal/tools-service/mcp"],
)
async def test_gateway_uses_initialized_mcp_session_for_discovery(
    monkeypatch, service_url: str
) -> None:
    events: list[str] = []
    received_headers: dict[str, str] = {}

    class FakeSession:
        async def initialize(self):
            events.append("initialize")

        async def list_tools(self, cursor=None):
            events.append("list_tools")
            return _Result(tools=[_Tool()], nextCursor=None)

    @asynccontextmanager
    async def fake_session(url: str, headers: dict[str, str]):
        assert url.endswith("/mcp")
        assert not url.endswith("/mcp/mcp")
        received_headers.update(headers)
        events.append("initialize")
        yield FakeSession()

    monkeypatch.setattr(gateway_module, "_open_mcp_session", fake_session)
    gateway = ToolsServiceToolGateway(service_url, "internal-secret")

    descriptors = await gateway.describe()

    assert events == ["initialize", "list_tools"]
    assert received_headers == {
        "Authorization": "Bearer internal-secret",
        "x-internal-token": "internal-secret",
    }
    assert descriptors[0].input_schema["required"] == ("datasource_id",)
    assert descriptors[0].input_schema["properties"]["path"] == {"type": "string"}


@pytest.mark.asyncio
async def test_binding_calls_tool_in_initialized_session_with_trusted_headers(monkeypatch) -> None:
    events: list[str] = []
    received_headers: dict[str, str] = {}
    call_tool = AsyncMock(
        return_value=_Result(
            content=[_Result(type="text", text="connector result")],
            isError=False,
        )
    )

    class FakeSession:
        async def initialize(self):
            events.append("initialize")

        async def list_tools(self, cursor=None):
            return _Result(tools=[_Tool()], nextCursor=None)

        async def call_tool(self, name, arguments):
            events.append("call_tool")
            return await call_tool(name, arguments)

    @asynccontextmanager
    async def fake_session(url: str, headers: dict[str, str]):
        received_headers.update(headers)
        events.append("initialize")
        yield FakeSession()

    monkeypatch.setattr(gateway_module, "_open_mcp_session", fake_session)
    gateway = ToolsServiceToolGateway("http://tools-service:8003", "internal-secret")
    binding = (await gateway.resolve(("connector_read",)))[0]

    result = await binding.invoke(
        ToolInvocation(
            model_arguments={"datasource_id": "source-1", "path": "README.md"},
            trusted_context=build_trusted_context(
                user_id="user-1",
                binding_references={"connectors.persona_id": "persona-9"},
            ),
        )
    )

    assert events[-2:] == ["initialize", "call_tool"]
    call_tool.assert_awaited_once_with(
        "connector_read",
        {"datasource_id": "source-1", "path": "README.md"},
    )
    assert received_headers["x-user-id"] == "user-1"
    assert received_headers["x-binding-ref-connectors.persona_id"] == "persona-9"
    assert received_headers["Authorization"] == "Bearer internal-secret"
    assert received_headers["x-internal-token"] == "internal-secret"
    assert result.output == ({"type": "text", "text": "connector result"},)


@pytest.mark.asyncio
async def test_binding_sanitizes_transport_failures(monkeypatch) -> None:
    @asynccontextmanager
    async def failing_session(url: str, headers: dict[str, str]):
        raise RuntimeError("internal-secret response body")
        yield

    monkeypatch.setattr(gateway_module, "_open_mcp_session", failing_session)
    gateway = ToolsServiceToolGateway("http://tools-service:8003", "internal-secret")
    gateway._cached_tools = [
        gateway_module.ToolDescriptor("connector_read", "Read", input_schema={})
    ]
    gateway._cache_expires_at = float("inf")
    binding = (await gateway.resolve(("connector_read",)))[0]

    with pytest.raises(Exception) as exc_info:
        await binding.invoke(ToolInvocation(model_arguments={"datasource_id": "source-1"}))

    assert str(exc_info.value) == "Tools service is unavailable"
    assert "internal-secret" not in str(exc_info.value)
