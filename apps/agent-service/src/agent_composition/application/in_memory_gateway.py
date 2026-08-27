from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..domain.ports import ToolBinding, ToolDescriptor, ToolInvocation, ToolResult


class InMemoryToolBinding:
    """Concrete ``ToolBinding`` for tests; never contacts a real MCP server."""

    def __init__(
        self,
        descriptor: ToolDescriptor,
        handler: Callable[[ToolInvocation], Awaitable[ToolResult]],
    ) -> None:
        self.descriptor = descriptor
        self._handler = handler

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        return await self._handler(invocation)


class InMemoryToolGateway:
    """In-memory ``ToolGateway`` used by contract tests.

    Implements the port without network, transport, or secret resolution.
    """

    def __init__(self, bindings: list[InMemoryToolBinding]) -> None:
        self._bindings = {binding.descriptor.key: binding for binding in bindings}
        self._loaded = False

    async def load(self) -> None:
        self._loaded = True

    async def describe(self) -> tuple[ToolDescriptor, ...]:
        return tuple(binding.descriptor for binding in self._bindings.values())

    async def resolve(self, keys: tuple[str, ...]) -> tuple[ToolBinding, ...]:
        resolved: list[ToolBinding] = []
        for key in keys:
            binding = self._bindings.get(key)
            if binding is not None:
                resolved.append(binding)
        return tuple(resolved)

    async def close(self) -> None:
        self._loaded = False
