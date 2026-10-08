"""Evidence packets carry an id; the hydrator fills their data from the thread's rows."""

from __future__ import annotations

from uuid import uuid4

import pytest

from service.knowledge_evidence.hydrator import KnowledgeEvidenceHydrator
from service.knowledge_evidence.packets import knowledge_tool_delta
from service.knowledge_evidence.presenter import KnowledgeEvidencePresenter
from service.knowledge_evidence.references import EVIDENCE_ARTIFACT_KEY, KNOWLEDGE_RESPONSE_TYPE

from .conftest import THREAD_ID, make_evidence


def test_knowledge_tool_delta_references_the_evidence() -> None:
    evidence_id = uuid4()

    packet = knowledge_tool_delta(tool_name="database_search", call_id="call-1", evidence_id=evidence_id)

    assert packet == {
        "type": "custom_tool_delta",
        "tool_name": "database_search",
        "response_type": KNOWLEDGE_RESPONSE_TYPE,
        "evidence_id": str(evidence_id),
        "data": None,
        "call_id": "call-1",
    }


@pytest.mark.asyncio
async def test_hydrate_fills_packets_of_the_thread(store) -> None:
    evidence_id = await store.add(THREAD_ID, make_evidence())
    packet = knowledge_tool_delta(tool_name="database_search", call_id="c", evidence_id=evidence_id)
    untouched = {"type": "custom_tool_delta", "response_type": "tool_result", "data": "plain"}

    await KnowledgeEvidenceHydrator(store).hydrate(THREAD_ID, [packet, untouched])

    assert packet["data"] == make_evidence().model_dump(mode="json")
    assert untouched == {"type": "custom_tool_delta", "response_type": "tool_result", "data": "plain"}


@pytest.mark.asyncio
async def test_hydrate_never_serves_another_threads_evidence(store) -> None:
    foreign_id = await store.add(uuid4(), make_evidence())
    packet = knowledge_tool_delta(tool_name="database_search", call_id="c", evidence_id=foreign_id)

    await KnowledgeEvidenceHydrator(store).hydrate(THREAD_ID, [packet])

    assert packet["data"] is None


@pytest.mark.asyncio
async def test_hydrate_survives_a_store_failure(store) -> None:
    packet = knowledge_tool_delta(tool_name="database_search", call_id="c", evidence_id=uuid4())
    store.fail_with = RuntimeError("database is down")

    await KnowledgeEvidenceHydrator(store).hydrate(THREAD_ID, [packet])

    assert packet["data"] is None


@pytest.mark.asyncio
async def test_hydrate_without_a_thread_leaves_packets_unfilled(store) -> None:
    evidence_id = await store.add(THREAD_ID, make_evidence())
    packet = knowledge_tool_delta(tool_name="database_search", call_id="c", evidence_id=evidence_id)

    await KnowledgeEvidenceHydrator(store).hydrate("not-a-uuid", [packet])

    assert packet["data"] is None


@pytest.mark.asyncio
async def test_hydrate_tree_reaches_wrapped_history_packets(store) -> None:
    evidence_id = await store.add(THREAD_ID, make_evidence())
    wrapped = {
        "placement": {"turn_index": 0},
        "obj": knowledge_tool_delta(tool_name="graph_search", call_id="c", evidence_id=evidence_id),
    }

    await KnowledgeEvidenceHydrator(store).hydrate_tree(str(THREAD_ID), [[wrapped], []])

    assert wrapped["obj"]["data"]["query"] == make_evidence().query


@pytest.mark.asyncio
async def test_presenter_turns_an_artifact_into_a_hydrated_packet(store) -> None:
    evidence_id = await store.add(THREAD_ID, make_evidence())
    presenter = KnowledgeEvidencePresenter(KnowledgeEvidenceHydrator(store), thread_id=str(THREAD_ID))

    packet = await presenter.tool_result_packet(
        tool_name="database_search",
        call_id="call-1",
        artifact={EVIDENCE_ARTIFACT_KEY: str(evidence_id)},
    )

    assert packet is not None
    assert packet["evidence_id"] == str(evidence_id)
    assert packet["data"] == make_evidence().model_dump(mode="json")


@pytest.mark.asyncio
async def test_presenter_ignores_results_without_evidence(store) -> None:
    presenter = KnowledgeEvidencePresenter(KnowledgeEvidenceHydrator(store), thread_id=str(THREAD_ID))

    assert await presenter.tool_result_packet(tool_name="calculator", call_id="c", artifact=None) is None
