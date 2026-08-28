from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from agent_composition.domain.definitions import AgentDefinition

RuntimeT = TypeVar("RuntimeT", bound="ClosableRuntime")


class ClosableRuntime(Protocol):
    async def close(self) -> None: ...


def fingerprint_definition(definition: AgentDefinition) -> str:
    """Return a deterministic runtime fingerprint for an agent definition.

    The semantic `version` field is intentionally excluded. Cache invalidation
    is based on normalized runtime-affecting fields and nested fingerprints.
    """
    payload = _definition_payload(definition)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _definition_payload(definition: AgentDefinition) -> dict[str, Any]:
    return {
        "brain": _dataclass_payload(definition.brain),
        "perceptrons": [_dataclass_payload(item) for item in definition.perceptrons],
        "tools": _dataclass_payload(definition.tools),
        "graph": _dataclass_payload(definition.graph),
        "runtime_policy": _dataclass_payload(definition.runtime_policy),
        "nested": [
            {
                "identity": nested.identity,
                "fingerprint": fingerprint_definition(nested),
            }
            for nested in definition.nested
        ],
    }


def _dataclass_payload(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: _dataclass_payload(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): _dataclass_payload(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_dataclass_payload(item) for item in value]
    return value


@dataclass
class _RuntimeEntry:
    fingerprint: str
    runtime: ClosableRuntime
    active_leases: int = 0
    retiring: bool = False


class AgentRuntimeCache:
    """Lease-aware runtime cache for composed dynamic agents."""

    def __init__(self) -> None:
        self._entries: dict[str, _RuntimeEntry] = {}
        self._retired: list[_RuntimeEntry] = []
        self._closed = False

    @asynccontextmanager
    async def lease(
        self,
        definition_id: str,
        fingerprint: str,
        factory: Callable[[], Awaitable[RuntimeT]],
    ) -> AsyncIterator[RuntimeT]:
        entry = await self._acquire(definition_id, fingerprint, factory)
        try:
            yield entry.runtime  # type: ignore[misc]
        finally:
            await self._release(entry)

    async def invalidate(self, definition_id: str) -> None:
        entry = self._entries.pop(definition_id, None)
        if entry is not None:
            await self._retire(entry)

    async def shutdown(self) -> None:
        self._closed = True
        current_entries = list(self._entries.values())
        self._entries.clear()
        for entry in current_entries:
            await self._retire(entry)
        for entry in list(self._retired):
            if entry.active_leases == 0:
                await self._close_entry(entry)

    async def _acquire(
        self,
        definition_id: str,
        fingerprint: str,
        factory: Callable[[], Awaitable[RuntimeT]],
    ) -> _RuntimeEntry:
        if self._closed:
            raise RuntimeError("AgentRuntimeCache is closed.")

        entry = self._entries.get(definition_id)
        if entry is not None and entry.fingerprint == fingerprint and not entry.retiring:
            entry.active_leases += 1
            return entry

        if entry is not None:
            self._entries.pop(definition_id, None)
            await self._retire(entry)

        runtime = await factory()
        new_entry = _RuntimeEntry(fingerprint=fingerprint, runtime=runtime)
        new_entry.active_leases = 1
        self._entries[definition_id] = new_entry
        return new_entry

    async def _release(self, entry: _RuntimeEntry) -> None:
        entry.active_leases -= 1
        if entry.active_leases == 0 and entry.retiring:
            await self._close_entry(entry)

    async def _retire(self, entry: _RuntimeEntry) -> None:
        entry.retiring = True
        if entry.active_leases == 0:
            await self._close_entry(entry)
        elif entry not in self._retired:
            self._retired.append(entry)

    async def _close_entry(self, entry: _RuntimeEntry) -> None:
        if entry in self._retired:
            self._retired.remove(entry)
        result = entry.runtime.close()
        if inspect.isawaitable(result):
            await result
