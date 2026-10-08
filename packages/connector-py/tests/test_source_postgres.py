"""PostgreSQL source: the connections of its pool decode JSON columns.

asyncpg hands ``json`` / ``jsonb`` values over as text unless a codec is registered;
discovery declares those columns as ``object``, so the records have to carry the
decoded value (found against a live PostgreSQL 18 on 2026-10-06).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from connector.sources import postgres as postgres_module
from connector.sources.postgres import PostgresSource


class FakeConnection:
    def __init__(self) -> None:
        self.codecs: list[tuple[str, str, Any, Any]] = []

    async def set_type_codec(
        self, typename: str, *, encoder: Any, decoder: Any, schema: str
    ) -> None:
        self.codecs.append((typename, schema, encoder, decoder))


@pytest.mark.asyncio
async def test_pool_connections_decode_json_and_jsonb_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def create_pool(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        postgres_module, "require_extra", lambda *a, **k: SimpleNamespace(create_pool=create_pool)
    )
    source = PostgresSource.from_config(
        {"host": "db", "database": "d", "username": "u", "password": "p"}
    )

    await source._get_pool()

    connection = FakeConnection()
    await captured["init"](connection)
    assert [(name, schema) for name, schema, _, _ in connection.codecs] == [
        ("json", "pg_catalog"),
        ("jsonb", "pg_catalog"),
    ]
    _, _, encoder, decoder = connection.codecs[1]
    assert decoder('{"n": 1, "nested": {"ok": true}}') == {"n": 1, "nested": {"ok": True}}
    assert encoder({"n": 1}) == '{"n": 1}'
