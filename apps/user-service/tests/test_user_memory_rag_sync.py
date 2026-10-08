"""Spec: every mutation to a user's stored facts must keep rag-service's
memory-facts semantic index in sync, since the *only* place agent-service's
chat-turn recall reads from is that index, not this service's own Postgres
table directly. This is the entry point for BOTH mutation paths: the
public CRUD API (direct manual add/edit/delete from the frontend) and the
internal API agent-service uses for auto-extracted facts -- both funnel
through UserMemoryService, so syncing here covers both.

Sync calls run as tracked background tasks (src.core.background_tasks):
a rag-service/Milvus hiccup must never fail the user-facing CRUD request
that triggered it.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from error_contract.domain import MemoryNotFoundError
import pytest

from src.core.background_tasks import _BACKGROUND_TASKS
from src.service.user_memory_service import UserMemoryService


@pytest.fixture(autouse=True)
def _clear_tasks():
    _BACKGROUND_TASKS.clear()
    yield
    _BACKGROUND_TASKS.clear()


async def _drain_background_tasks() -> None:
    if _BACKGROUND_TASKS:
        await asyncio.wait_for(
            asyncio.gather(*list(_BACKGROUND_TASKS), return_exceptions=True), timeout=1.0
        )


def _service() -> UserMemoryService:
    service = UserMemoryService.__new__(UserMemoryService)
    service.repo = AsyncMock()
    return service


def _row(row_id, content, **kwargs) -> MagicMock:
    return MagicMock(
        id=row_id,
        user_id=kwargs.get("user_id"),
        content=content,
        source=kwargs.get("source", "manual"),
        time_created=None,
        time_updated=None,
    )


@pytest.mark.asyncio
async def test_create_syncs_the_new_fact_to_rag_service(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.upsert_fact", upsert)

    service = _service()
    user_id = uuid.uuid4()
    fact_id = uuid.uuid4()
    service.repo.create = AsyncMock(return_value=_row(fact_id, "User likes tea"))

    await service.create(user_id, "User likes tea")
    await _drain_background_tasks()

    upsert.assert_awaited_once_with(
        user_id=str(user_id), fact_id=str(fact_id), content="User likes tea"
    )


@pytest.mark.asyncio
async def test_add_facts_syncs_every_created_fact(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.upsert_fact", upsert)

    service = _service()
    user_id = uuid.uuid4()
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    service.repo.bulk_create = AsyncMock(
        return_value=[_row(id1, "fact one"), _row(id2, "fact two")]
    )
    service.repo.delete_oldest_excess = AsyncMock(return_value=0)

    await service.add_facts(user_id, ["fact one", "fact two"])
    await _drain_background_tasks()

    assert upsert.await_count == 2
    upsert.assert_any_await(user_id=str(user_id), fact_id=str(id1), content="fact one")
    upsert.assert_any_await(user_id=str(user_id), fact_id=str(id2), content="fact two")


@pytest.mark.asyncio
async def test_add_facts_with_nothing_created_does_not_sync(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.upsert_fact", upsert)

    service = _service()
    service.repo.bulk_create = AsyncMock(return_value=[])

    await service.add_facts(uuid.uuid4(), ["duplicate fact"])
    await _drain_background_tasks()

    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_syncs_the_re_embedded_fact(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.upsert_fact", upsert)

    service = _service()
    user_id = uuid.uuid4()
    fact_id = uuid.uuid4()
    service.repo.update = AsyncMock(return_value=_row(fact_id, "updated content"))

    await service.update(fact_id, user_id, "updated content")
    await _drain_background_tasks()

    upsert.assert_awaited_once_with(
        user_id=str(user_id), fact_id=str(fact_id), content="updated content"
    )


@pytest.mark.asyncio
async def test_update_with_no_matching_row_does_not_sync(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.upsert_fact", upsert)

    service = _service()
    service.repo.update = AsyncMock(return_value=None)

    with pytest.raises(MemoryNotFoundError):
        await service.update(uuid.uuid4(), uuid.uuid4(), "content")
    await _drain_background_tasks()

    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_syncs_the_deletion_to_rag_service(monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.delete_fact", delete)

    service = _service()
    user_id = uuid.uuid4()
    fact_id = uuid.uuid4()
    service.repo.delete = AsyncMock(return_value=True)

    await service.delete(fact_id, user_id)
    await _drain_background_tasks()

    delete.assert_awaited_once_with(user_id=str(user_id), fact_id=str(fact_id))


@pytest.mark.asyncio
async def test_delete_with_nothing_deleted_does_not_sync(monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.delete_fact", delete)

    service = _service()
    service.repo.delete = AsyncMock(return_value=False)

    with pytest.raises(MemoryNotFoundError):
        await service.delete(uuid.uuid4(), uuid.uuid4())
    await _drain_background_tasks()

    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_all_syncs_to_rag_service(monkeypatch):
    delete_all = AsyncMock()
    monkeypatch.setattr(
        "src.service.user_memory_service.rag_memory_client.delete_all_facts", delete_all
    )

    service = _service()
    user_id = uuid.uuid4()
    service.repo.delete_all = AsyncMock(return_value=3)

    await service.delete_all(user_id)
    await _drain_background_tasks()

    delete_all.assert_awaited_once_with(user_id=str(user_id))


@pytest.mark.asyncio
async def test_delete_all_with_nothing_deleted_does_not_sync(monkeypatch):
    delete_all = AsyncMock()
    monkeypatch.setattr(
        "src.service.user_memory_service.rag_memory_client.delete_all_facts", delete_all
    )

    service = _service()
    service.repo.delete_all = AsyncMock(return_value=0)

    await service.delete_all(uuid.uuid4())
    await _drain_background_tasks()

    delete_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_rag_service_sync_failure_does_not_raise(monkeypatch):
    # Fail-open by design: a Milvus/rag-service hiccup must not surface as
    # an error on the CRUD response that triggered the sync.
    upsert = AsyncMock(side_effect=RuntimeError("connection refused"))
    monkeypatch.setattr("src.service.user_memory_service.rag_memory_client.upsert_fact", upsert)

    service = _service()
    fact_id = uuid.uuid4()
    service.repo.create = AsyncMock(return_value=_row(fact_id, "content"))

    result = await service.create(uuid.uuid4(), "content")
    await _drain_background_tasks()

    assert result["content"] == "content"
    upsert.assert_awaited_once()
