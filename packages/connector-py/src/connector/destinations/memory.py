"""In-memory destination for tests and dry runs."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from ..base import BaseDestination
from ..models import (
    Batch,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    WriteResult,
)


class InMemoryDestinationConfig(BaseModel):
    fail_first_n_batches: int = 0
    """Testing aid: raise on the first N write calls to exercise retries."""


class InMemoryDestination(BaseDestination[InMemoryDestinationConfig]):
    definition = ConnectorDefinition(
        name="memory",
        icon="memory.svg",
        display_name="In-Memory (testing)",
        kind=ConnectorKind.DESTINATION,
        category=ConnectorCategory.TESTING,
        tags=frozenset({"testing"}),
    )
    Config = InMemoryDestinationConfig

    # Class-level sink so a runner that builds the destination from a registry
    # and a test can share the written data.
    sink: dict[str, list[dict[str, Any]]] = {}
    batches: list[Batch] = []
    events: list[tuple[str, str | None]] = []
    """Lifecycle calls in order: ``("begin" | "finalize" | "abort", job_id)``."""
    max_records_per_stream: ClassVar[int] = 100_000
    max_batches: ClassVar[int] = 1_000
    """Bounds for a long-lived process that keeps dry-running: the oldest entries go."""
    _failures_left: int = 0

    def __init__(self, config: InMemoryDestinationConfig) -> None:
        super().__init__(config)
        type(self)._failures_left = config.fail_first_n_batches

    @classmethod
    def reset(cls) -> None:
        cls.sink = {}
        cls.batches = []
        cls.events = []
        cls._failures_left = 0

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    @classmethod
    def _event(cls, name: str, job_id: str | None) -> None:
        cls.events.append((name, job_id))
        del cls.events[: max(len(cls.events) - cls.max_batches, 0)]

    async def begin(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> None:
        self._event("begin", job_id)
        for s in catalog.streams:
            if s.destination_sync_mode.value == "overwrite":
                type(self).sink[s.stream.name] = []

    async def finalize(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> None:
        self._event("finalize", job_id)

    async def abort(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        self._event("abort", job_id)

    async def write(self, batch: Batch) -> WriteResult:
        cls = type(self)
        if cls._failures_left > 0:
            cls._failures_left -= 1
            raise ConnectionError("simulated destination failure")
        cls.batches.append(batch)
        del cls.batches[: max(len(cls.batches) - cls.max_batches, 0)]
        rows = cls.sink.setdefault(batch.stream, [])
        rows.extend(r.data for r in batch.records)
        del rows[: max(len(rows) - cls.max_records_per_stream, 0)]
        return WriteResult(records_written=batch.size)
