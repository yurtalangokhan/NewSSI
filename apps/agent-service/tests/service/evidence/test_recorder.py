"""KnowledgeEvidenceRecorder: persisting evidence must never break a tool call."""

from __future__ import annotations

import pytest

from service.knowledge_evidence.recorder import KnowledgeEvidenceRecorder

from .conftest import THREAD_ID, make_evidence


@pytest.mark.asyncio
async def test_records_under_the_current_thread(store) -> None:
    recorder = KnowledgeEvidenceRecorder(store, thread_id_provider=lambda: THREAD_ID)

    evidence_id = await recorder.record(make_evidence())

    assert store.rows[evidence_id] == (THREAD_ID, make_evidence())


@pytest.mark.asyncio
async def test_explicit_thread_wins_over_the_provider(store) -> None:
    recorder = KnowledgeEvidenceRecorder(store, thread_id_provider=lambda: None)

    evidence_id = await recorder.record(make_evidence(), thread_id=THREAD_ID)

    assert store.rows[evidence_id][0] == THREAD_ID


@pytest.mark.asyncio
async def test_without_a_thread_nothing_is_recorded(store) -> None:
    recorder = KnowledgeEvidenceRecorder(store, thread_id_provider=lambda: None)

    assert await recorder.record(make_evidence()) is None
    assert store.rows == {}


@pytest.mark.asyncio
async def test_a_store_failure_is_swallowed(store) -> None:
    store.fail_with = RuntimeError("database is down")
    recorder = KnowledgeEvidenceRecorder(store, thread_id_provider=lambda: THREAD_ID)

    assert await recorder.record(make_evidence()) is None
