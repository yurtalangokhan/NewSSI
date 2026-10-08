"""``CollectionsManager.delete_mutable`` drops the collection's Milvus table before its row.

The row is what names the table: once it is gone nothing could reach the chunks
any more (orphaned tables seen in Milvus). The table goes first, so a drop that
fails keeps the row and the delete can be repeated once Milvus is back.
"""

import pytest
from error_contract import DependencyUnavailableError

from src.collections import service as collections_service
from src.collections import write_guards
from src.documents import service as documents_service


def _manager(
    monkeypatch,
    events: list[str],
    *,
    exists: bool = True,
    drop_error: Exception | None = None,
) -> collections_service.CollectionsManager:
    manager = collections_service.CollectionsManager("user-id")

    async def get(collection_id, required_permission="read"):
        events.append(f"get:{required_permission}")
        return {"uuid": collection_id, "table_id": "milvus-table"} if exists else None

    async def delete(collection_id):
        events.append("delete")
        return 1

    async def drop(self):
        events.append(f"drop:{self.collection_id}:{self.user_id}")
        if drop_error is not None:
            raise drop_error
        return 3

    async def not_connector_managed(collection_id):
        events.append("guard:connector")

    def mutable(collection_id):
        events.append("guard:mutable")

    monkeypatch.setattr(manager, "get", get)
    monkeypatch.setattr(manager, "delete", delete)
    monkeypatch.setattr(documents_service.Collection, "drop", drop)
    monkeypatch.setattr(write_guards, "ensure_not_connector_managed_collection", not_connector_managed)
    monkeypatch.setattr(write_guards, "ensure_collection_mutable", mutable)
    return manager


@pytest.mark.asyncio
async def test_delete_drops_the_milvus_table_before_the_row(monkeypatch) -> None:
    events: list[str] = []
    manager = _manager(monkeypatch, events)

    await manager.delete_mutable("col-1")

    # guards, then the caller's right to administer, then the table, then the row
    assert events == ["guard:connector", "guard:mutable", "get:admin", "drop:col-1:user-id", "delete"]


@pytest.mark.asyncio
async def test_a_failing_drop_keeps_the_row(monkeypatch) -> None:
    events: list[str] = []
    manager = _manager(monkeypatch, events, drop_error=DependencyUnavailableError())

    with pytest.raises(DependencyUnavailableError):
        await manager.delete_mutable("col-1")

    assert "delete" not in events


@pytest.mark.asyncio
async def test_a_missing_or_inaccessible_collection_drops_nothing(monkeypatch) -> None:
    # Deleting what is not there (or not the caller's) stays a silent no-op: the
    # route answers 200 and the delete is idempotent.
    events: list[str] = []
    manager = _manager(monkeypatch, events, exists=False)

    await manager.delete_mutable("col-1")

    assert events == ["guard:connector", "guard:mutable", "get:admin"]


@pytest.mark.asyncio
async def test_force_skips_only_the_connector_guard(monkeypatch) -> None:
    events: list[str] = []
    manager = _manager(monkeypatch, events)

    await manager.delete_mutable("col-1", force=True)

    assert events == ["guard:mutable", "get:admin", "drop:col-1:user-id", "delete"]
