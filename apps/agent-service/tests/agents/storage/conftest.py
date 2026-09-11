"""Shared DB-session fixtures for agents/storage tests (P3, Tasks 14-17).

No existing test in this suite spins up a real SQLAlchemy engine — model
tests so far only exercised pure Python (Task 1) or used fakes (Task 6, 15+).
Task 14 needs real behavioral guarantees (a duplicate version_no actually
raises IntegrityError; deleting a definition actually cascades) that no fake
can prove.

Full ``Base.metadata.create_all`` doesn't work here: unrelated models
(``agent_groups.user_ids``) use ``postgresql.JSONB``, which SQLite's DDL
compiler rejects outright. Instead this fixture creates only the two tables
under test — SQLite compiles these fine once JSONB is rendered as plain
JSON (shim below); production runs Postgres, where JSONB is native. The
shim is required since dev's 0028 alignment switched AgentDefinitionModel's
list/dict columns (mcp_tools, rag_config, ...) from ``sqlalchemy.JSON`` to
``postgresql.JSONB``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _render_jsonb_as_json_on_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN003, ARG001
    """Render postgresql.JSONB as plain JSON under the SQLite test engine."""
    return "JSON"


@pytest_asyncio.fixture
async def flow_version_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """A real SQLite in-memory engine with FK enforcement on, scoped to just
    AgentDefinitionModel + AgentFlowVersionModel."""
    from core.db.models.agent_definition import AgentDefinitionModel, AgentFlowVersionModel

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(AgentDefinitionModel.__table__.create)
        await conn.run_sync(AgentFlowVersionModel.__table__.create)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def patched_repository_session(flow_version_session_factory, monkeypatch):
    """Point BaseRepository._session() at the SQLite test engine.

    core/db/repositories/base.py imports get_session_factory by reference at
    module load time, so patching core.db.engine.get_session_factory alone
    would not be observed there — the repositories module's own binding must
    be patched.
    """
    import core.db.repositories.base as base_module

    monkeypatch.setattr(base_module, "get_session_factory", lambda: flow_version_session_factory)
    return flow_version_session_factory
