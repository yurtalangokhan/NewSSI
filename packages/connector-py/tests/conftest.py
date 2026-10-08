from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from connector import (
    BaseSource,
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    ConnectorRegistry,
    Record,
    RuntimeOverrides,
    State,
    Stream,
    SyncMode,
    SyncState,
)
from connector.destinations.memory import InMemoryDestination


class FakeConfig(BaseModel):
    rows: int = 5
    streams: list[str] = ["a"]


class FakeSource(BaseSource[FakeConfig]):
    """Deterministic source emitting ``rows`` records per stream plus a State."""

    definition = ConnectorDefinition(
        name="fake",
        display_name="Fake",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TESTING,
        tags=frozenset({"testing"}),
    )
    Config = FakeConfig

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name=s,
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    default_cursor_field=["id"],
                )
                for s in self.config.streams
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        for cs in catalog.streams:
            name = cs.stream.name
            start = int(state.get(name).get("cursor", 0))
            for i in range(start + 1, start + self.config.rows + 1):
                yield Record(stream=name, data={"id": i, "stream": name})
            yield State(stream=name, data={"cursor": start + self.config.rows})


@pytest.fixture
def registry() -> ConnectorRegistry:
    reg = ConnectorRegistry(overrides=RuntimeOverrides())
    reg.register(FakeSource)
    reg.register(InMemoryDestination)
    InMemoryDestination.reset()
    return reg


@pytest.fixture
def jsonl_dir(tmp_path: Path) -> Path:
    users = tmp_path / "users.jsonl"
    users.write_text(
        "\n".join(
            json.dumps({"id": i, "name": f"u{i}", "updated_at": i * 10}) for i in range(1, 6)
        ),
        encoding="utf-8",
    )
    orders = tmp_path / "orders.jsonl"
    orders.write_text(
        "\n".join(json.dumps({"id": i, "total": i * 1.5, "updated_at": i}) for i in range(1, 4)),
        encoding="utf-8",
    )
    return tmp_path
