"""An API key may only be revoked or deleted by the user who owns it.

`api_key:delete` means "may delete API keys", not "may delete anyone's API
keys" — every enduser holds it for their own keys. Filtering the statement on
`id` alone turned that into a cross-tenant revoke: knowing (or guessing)
another user's key id was enough to cut off their access.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, text

from src.repository.api_key_repository import ApiKeyRepository

OWNER = uuid.uuid4()
ATTACKER = uuid.uuid4()
KEY_ID = uuid.uuid4()


def _seeded_connection():
    engine = create_engine("sqlite://")
    connection = engine.connect()
    connection.execute(
        text(
            "CREATE TABLE api_keys (id UUID, user_id UUID, key_hash TEXT, "
            "key_prefix TEXT, name TEXT, is_active BOOLEAN)"
        )
    )
    connection.execute(
        text("INSERT INTO api_keys VALUES (:id, :user_id, 'hash', 'sk_test', 'k', 1)"),
        {"id": KEY_ID.hex, "user_id": OWNER.hex},
    )
    return connection


def _repository_on(connection) -> ApiKeyRepository:
    repository = ApiKeyRepository()

    @asynccontextmanager
    async def session():
        yield SimpleNamespace(execute=AsyncMock(side_effect=connection.execute))

    repository._session = session
    return repository


def _row_count(connection) -> int:
    return connection.execute(
        text("SELECT COUNT(*) FROM api_keys WHERE id = :id"), {"id": KEY_ID.hex}
    ).scalar()


def _is_active(connection) -> bool:
    return bool(
        connection.execute(
            text("SELECT is_active FROM api_keys WHERE id = :id"), {"id": KEY_ID.hex}
        ).scalar()
    )


async def test_delete_refuses_a_key_owned_by_someone_else():
    connection = _seeded_connection()
    with connection:
        assert await _repository_on(connection).delete(KEY_ID, ATTACKER) is False
        assert _row_count(connection) == 1, "another user's key was deleted"


async def test_delete_removes_the_callers_own_key():
    connection = _seeded_connection()
    with connection:
        assert await _repository_on(connection).delete(KEY_ID, OWNER) is True
        assert _row_count(connection) == 0


async def test_revoke_refuses_a_key_owned_by_someone_else():
    connection = _seeded_connection()
    with connection:
        assert await _repository_on(connection).revoke(KEY_ID, ATTACKER) is False
        assert _is_active(connection) is True, "another user's key was revoked"


async def test_revoke_deactivates_the_callers_own_key():
    connection = _seeded_connection()
    with connection:
        assert await _repository_on(connection).revoke(KEY_ID, OWNER) is True
        assert _is_active(connection) is False
