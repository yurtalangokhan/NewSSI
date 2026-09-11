"""Unit tests for the external-MCP repositories (plan task 2).

The repositories are exercised with a mocked ``_session`` context manager so no
real database is required (matches this repo's test conventions).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db.repositories.mcp_oauth_session_repo import MCPOAuthSessionRepository
from core.db.repositories.mcp_provider_auth_repo import MCPProviderAuthRepository
from core.db.repositories.mcp_provider_repo import MCPProviderRepository
from core.db.repositories.mcp_tool_repo import MCPToolRepository

PROVIDER_UUID = "11111111-1111-1111-1111-111111111111"


def _session_cm(session: AsyncMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_provider_auth_upsert_inserts_when_missing():
    repo = MCPProviderAuthRepository()
    session = AsyncMock()
    # first execute -> lookup (nothing), second execute -> insert returning row
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(
                scalar_one=MagicMock(
                    return_value=MagicMock(
                        id="row-1",
                        provider_id=PROVIDER_UUID,
                        user_id="user-abc",
                        credentials_encrypted="ct",
                        oauth_access_token_encrypted=None,
                        oauth_refresh_token_encrypted=None,
                        oauth_expires_at=None,
                        oauth_scopes=None,
                        time_created=None,
                        time_updated=None,
                    )
                )
            ),
        ]
    )
    with patch.object(MCPProviderAuthRepository, "_session", return_value=_session_cm(session)):
        out = await repo.upsert(PROVIDER_UUID, "user-abc", credentials_encrypted="ct")
    assert session.execute.await_count == 2
    assert out["credentials_encrypted"] == "ct"


@pytest.mark.asyncio
async def test_oauth_session_get_filters_expired():
    repo = MCPOAuthSessionRepository()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    with patch.object(MCPOAuthSessionRepository, "_session", return_value=_session_cm(session)):
        assert await repo.get("deadbeef") is None
    stmt = session.execute.await_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "expires_at" in compiled and "now()" in compiled.lower()


@pytest.mark.asyncio
async def test_oauth_session_sweep_expired_returns_rowcount():
    repo = MCPOAuthSessionRepository()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=4))
    with patch.object(MCPOAuthSessionRepository, "_session", return_value=_session_cm(session)):
        assert await repo.sweep_expired() == 4


@pytest.mark.asyncio
async def test_provider_set_status_updates_server_status_column():
    repo = MCPProviderRepository()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    with patch.object(MCPProviderRepository, "_session", return_value=_session_cm(session)):
        ok = await repo.set_status(PROVIDER_UUID, "CONNECTED")
    assert ok is True
    stmt = session.execute.await_args[0][0]
    assert "server_status" in str(stmt)


@pytest.mark.asyncio
async def test_provider_get_by_int_id_queries_int_id():
    repo = MCPProviderRepository()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    with patch.object(MCPProviderRepository, "_session", return_value=_session_cm(session)):
        assert await repo.get_by_int_id(1000) is None
    stmt = session.execute.await_args[0][0]
    assert "int_id" in str(stmt)


@pytest.mark.asyncio
async def test_provider_create_accepts_auth_fields():
    repo = MCPProviderRepository()
    captured = {}
    row = MagicMock(
        id="u",
        int_id=1000,
        name="n",
        type="external",
        url="https://x/mcp",
        transport="streamable_http",
        config={},
        is_active=True,
        is_builtin=False,
        description="",
        auth_type="OAUTH",
        auth_performer="PER_USER",
        server_status="CREATED",
        auth_template=None,
        owner_email="a@acme.io",
        oauth_metadata=None,
        time_created=None,
        time_updated=None,
    )
    session = AsyncMock()

    async def _exec(stmt):
        captured["values"] = dict(stmt.compile().params)
        return MagicMock(scalar_one=MagicMock(return_value=row))

    session.execute = AsyncMock(side_effect=_exec)
    with patch.object(MCPProviderRepository, "_session", return_value=_session_cm(session)):
        out = await repo.create(
            name="n",
            url="https://x/mcp",
            auth_type="OAUTH",
            auth_performer="PER_USER",
            owner_email="a@acme.io",
        )
    assert out["auth_type"] == "OAUTH"
    assert out["int_id"] == 1000
    assert captured["values"]["auth_type"] == "OAUTH"
    assert captured["values"]["owner_email"] == "a@acme.io"


@pytest.mark.asyncio
async def test_tool_set_enabled_returns_rowcount():
    repo = MCPToolRepository()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=3))
    with patch.object(MCPToolRepository, "_session", return_value=_session_cm(session)):
        n = await repo.set_enabled([1000, 1001, 1002], False)
    assert n == 3
    stmt = session.execute.await_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "enabled" in compiled and "int_id" in compiled


@pytest.mark.asyncio
async def test_tool_to_dict_exposes_int_id_and_enabled():
    row = MagicMock(
        id="u",
        provider_id="p",
        name="a",
        description="",
        input_schema={},
        output_schema={},
        tool_metadata={},
        category=None,
        tags=[],
        int_id=1000,
        enabled=True,
        is_active=True,
        last_synced=None,
        time_created=None,
    )
    d = MCPToolRepository._to_dict(row)
    assert d["int_id"] == 1000
    assert d["enabled"] is True


@pytest.mark.asyncio
async def test_bulk_upsert_conflict_set_uses_real_metadata_column():
    """Regression: the DO UPDATE SET clause must name the DB column ``metadata``,
    not the ORM attribute ``tool_metadata`` (which is not a real column)."""
    repo = MCPToolRepository()
    session = AsyncMock()
    captured: dict = {}

    async def _exec(stmt):
        captured["sql"] = str(stmt)
        return MagicMock(scalar_one_or_none=MagicMock(return_value=object()))

    session.execute = AsyncMock(side_effect=_exec)
    with patch.object(MCPToolRepository, "_session", return_value=_session_cm(session)):
        n = await repo.bulk_upsert(
            "11111111-1111-1111-1111-111111111111",
            [{"name": "t", "description": "d", "input_schema": {}}],
        )

    assert n == 1, "bulk_upsert silently swallowed the write"
    sql = captured["sql"]
    do_update = sql.split("ON CONFLICT", 1)[1]
    assert "tool_metadata" not in do_update, do_update
    assert "provider_id" in sql and "name" in sql


@pytest.mark.asyncio
async def test_bulk_upsert_conflict_targets_uq_mcp_tool_provider_name():
    """The conflict arbiter must be the (provider_id, name) unique constraint
    that migration 0043 adds."""
    repo = MCPToolRepository()
    session = AsyncMock()
    captured: dict = {}

    async def _exec(stmt):
        captured["sql"] = str(stmt)
        return MagicMock(scalar_one_or_none=MagicMock(return_value=object()))

    session.execute = AsyncMock(side_effect=_exec)
    with patch.object(MCPToolRepository, "_session", return_value=_session_cm(session)):
        await repo.bulk_upsert(
            "11111111-1111-1111-1111-111111111111",
            [{"name": "t", "description": "d", "input_schema": {}}],
        )

    assert "ON CONFLICT (provider_id, name)" in captured["sql"]
