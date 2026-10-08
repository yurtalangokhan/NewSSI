"""A provider id that is not a UUID is simply unknown, not a database error."""

from __future__ import annotations

import pytest

from infrastructure.db.repositories.mcp_provider_repo import MCPProviderRepository


@pytest.mark.asyncio
async def test_a_non_uuid_id_resolves_to_none_without_touching_the_database(monkeypatch):
    repo = MCPProviderRepository()

    def _no_session(*_args, **_kwargs):
        raise AssertionError("a malformed id must not reach the database")

    monkeypatch.setattr(repo, "_read_session", _no_session)

    assert await repo.get_by_id("not-a-uuid") is None
