"""Graph builds must expire when crashed, time out LLM calls, and survive shutdown.

Spec 5/T7: a build stuck in "extracting" (process killed, task collected)
locked its collection until the progress record's TTL eventually evicted
it; entity extraction had no timeout, so one hung LLM call blocked the
build loop forever between its only cancellation checkpoints; and
fire-and-forget background builds held no reference shutdown could reach.
"""

import asyncio
import time

import pytest

from src.collections import write_guards
from src.graph import service as graph_rag_service
from src.graph.schemas import BuildProgress, BuildStatus
from src.graph.service import (
    _build_heartbeats,
    _build_progress,
    cancel_all_background_tasks,
    is_build_stale,
    spawn_tracked,
)


@pytest.fixture(autouse=True)
def _clean_build_state():
    _build_progress.clear()
    _build_heartbeats.clear()
    yield
    _build_progress.clear()
    _build_heartbeats.clear()


def _register(collection_id: str, status: BuildStatus = BuildStatus.EXTRACTING) -> None:
    _build_progress[collection_id] = BuildProgress(
        collection_id=collection_id, status=status
    )
    _build_heartbeats[collection_id] = time.monotonic()


def test_a_build_with_a_recent_heartbeat_is_not_stale():
    _register("col-1")
    assert is_build_stale("col-1") is False


def test_a_build_with_no_recent_heartbeat_is_stale(monkeypatch):
    _register("col-1")
    monkeypatch.setattr(graph_rag_service, "_STALE_BUILD_SECONDS", 0.05)
    time.sleep(0.1)
    assert is_build_stale("col-1") is True


def test_ensure_collection_mutable_ignores_a_stale_build(monkeypatch):
    _register("col-1")
    monkeypatch.setattr(graph_rag_service, "_STALE_BUILD_SECONDS", 0.05)
    time.sleep(0.1)
    # A crashed builder must not lock the collection forever.
    write_guards.ensure_collection_mutable("col-1")


def test_ensure_collection_mutable_blocks_a_live_build():
    from error_contract import ConflictError

    _register("col-1")
    with pytest.raises(ConflictError):
        write_guards.ensure_collection_mutable("col-1")


async def test_extraction_has_a_timeout(monkeypatch):
    from src.graph.entity_extractor import EntityExtractor

    extractor = EntityExtractor(timeout_s=0.1)

    class _HangingTransformer:
        async def aconvert_to_graph_documents(self, _docs):
            await asyncio.sleep(60)

    monkeypatch.setattr(extractor, "_transformer", _HangingTransformer())

    started = time.monotonic()
    result = await extractor.extract_from_text("some text", chunk_id="c1")
    elapsed = time.monotonic() - started

    assert elapsed < 2
    assert result.entities == []
    assert result.relations == []


async def test_spawn_tracked_keeps_a_reference_until_done():
    done = asyncio.Event()

    async def _work():
        await done.wait()

    task = spawn_tracked(_work())
    assert task in graph_rag_service._BACKGROUND_TASKS

    done.set()
    await task
    assert task not in graph_rag_service._BACKGROUND_TASKS


async def test_cancel_all_background_tasks_cancels_in_flight_builds():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _work():
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    spawn_tracked(_work())
    await started.wait()

    await cancel_all_background_tasks()

    assert cancelled.is_set()
    assert set() == graph_rag_service._BACKGROUND_TASKS


async def test_start_build_reports_already_in_progress_only_for_a_genuinely_active_build(
    monkeypatch,
):
    class _FakeCollection:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def count(self) -> int:
            return 1

    monkeypatch.setattr(graph_rag_service, "Collection", _FakeCollection)

    _, already_in_progress = await graph_rag_service.start_build(
        collection_id="col-fresh", user_id="u1"
    )
    assert already_in_progress is False

    _register("col-active")
    _, already_in_progress = await graph_rag_service.start_build(
        collection_id="col-active", user_id="u1"
    )
    assert already_in_progress is True
