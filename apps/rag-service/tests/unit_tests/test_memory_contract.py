"""Pure-logic tests for src.memory.contract -- the port-injected
service that authorizes and executes fact-embedding writes and semantic
search, independent of Milvus/HTTP. Mirrors src.retrieval.contract's
testing style (fake ports, no FastAPI, no real vector store).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from error_contract import ForbiddenError, ValidationFailedError

from src.memory.contract import (
    DEFAULT_VECTOR_FLOOR,
    MAX_SEARCH_LIMIT,
    MemoryFactHit,
    MemoryIndexService,
    TrustedMemoryContext,
    bound_limit,
)


def _service(
    *, upsert=None, delete=None, delete_all=None, search=None
) -> MemoryIndexService:
    return MemoryIndexService(
        upsert=upsert or AsyncMock(),
        delete=delete or AsyncMock(),
        delete_all=delete_all or AsyncMock(),
        search=search or AsyncMock(return_value=()),
    )


def test_bound_limit_clamps_below_one():
    assert bound_limit(0) == 1
    assert bound_limit(-5) == 1


def test_bound_limit_clamps_above_max():
    assert bound_limit(MAX_SEARCH_LIMIT + 100) == MAX_SEARCH_LIMIT


def test_bound_limit_leaves_in_range_values_unchanged():
    assert bound_limit(5) == 5


async def test_upsert_calls_the_port_with_stripped_fields():
    upsert = AsyncMock()
    service = _service(upsert=upsert)

    await service.upsert_fact(
        TrustedMemoryContext(user_id="user-1"),
        fact_id="  fact-1  ",
        content="  User likes tea  ",
    )

    upsert.assert_awaited_once_with(
        user_id="user-1", fact_id="fact-1", content="User likes tea"
    )


async def test_upsert_rejects_empty_content():
    upsert = AsyncMock()
    service = _service(upsert=upsert)

    with pytest.raises(ValidationFailedError):
        await service.upsert_fact(
            TrustedMemoryContext(user_id="user-1"), fact_id="fact-1", content="   "
        )
    upsert.assert_not_awaited()


async def test_upsert_rejects_empty_fact_id():
    upsert = AsyncMock()
    service = _service(upsert=upsert)

    with pytest.raises(ValidationFailedError):
        await service.upsert_fact(
            TrustedMemoryContext(user_id="user-1"), fact_id="  ", content="content"
        )
    upsert.assert_not_awaited()


async def test_upsert_requires_a_trusted_user():
    upsert = AsyncMock()
    service = _service(upsert=upsert)

    with pytest.raises(ForbiddenError):
        await service.upsert_fact(
            TrustedMemoryContext(user_id=""), fact_id="fact-1", content="content"
        )
    upsert.assert_not_awaited()


async def test_delete_calls_the_port():
    delete = AsyncMock()
    service = _service(delete=delete)

    await service.delete_fact(TrustedMemoryContext(user_id="user-1"), fact_id="fact-1")

    delete.assert_awaited_once_with(user_id="user-1", fact_id="fact-1")


async def test_delete_rejects_empty_fact_id():
    delete = AsyncMock()
    service = _service(delete=delete)

    with pytest.raises(ValidationFailedError):
        await service.delete_fact(TrustedMemoryContext(user_id="user-1"), fact_id="")
    delete.assert_not_awaited()


async def test_delete_all_calls_the_port_for_the_trusted_user():
    delete_all = AsyncMock()
    service = _service(delete_all=delete_all)

    await service.delete_all_facts(TrustedMemoryContext(user_id="user-1"))

    delete_all.assert_awaited_once_with(user_id="user-1")


async def test_delete_all_requires_a_trusted_user():
    delete_all = AsyncMock()
    service = _service(delete_all=delete_all)

    with pytest.raises(ForbiddenError):
        await service.delete_all_facts(TrustedMemoryContext(user_id=""))
    delete_all.assert_not_awaited()


async def test_search_returns_hits_from_the_port():
    hits = (MemoryFactHit(fact_id="f1", content="User likes tea", score=0.9),)
    search = AsyncMock(return_value=hits)
    service = _service(search=search)

    result = await service.search_facts(
        TrustedMemoryContext(user_id="user-1"), query="what do I like to drink"
    )

    assert len(result) == 1
    assert result[0].fact_id == "f1"
    assert result[0].content == "User likes tea"
    # score is now the fused RRF value, with the port's cosine kept alongside it
    assert result[0].vector_score == 0.9
    search.assert_awaited_once_with(user_id="user-1", query="what do I like to drink", limit=5)


async def test_search_filters_out_hits_below_the_vector_floor():
    hits = (
        MemoryFactHit(fact_id="f1", content="relevant", score=0.9),
        MemoryFactHit(fact_id="f2", content="noise", score=0.1),
    )
    search = AsyncMock(return_value=hits)
    service = _service(search=search)

    result = await service.search_facts(
        TrustedMemoryContext(user_id="user-1"), query="q", vector_floor=0.5
    )

    assert len(result) == 1
    assert result[0].fact_id == "f1"


async def test_search_with_a_blank_query_returns_nothing_without_calling_the_port():
    search = AsyncMock()
    service = _service(search=search)

    result = await service.search_facts(TrustedMemoryContext(user_id="user-1"), query="   ")

    assert result == ()
    search.assert_not_awaited()


async def test_search_requires_a_trusted_user():
    search = AsyncMock()
    service = _service(search=search)

    with pytest.raises(ForbiddenError):
        await service.search_facts(TrustedMemoryContext(user_id=""), query="q")
    search.assert_not_awaited()


async def test_search_clamps_an_out_of_range_limit():
    search = AsyncMock(return_value=())
    service = _service(search=search)

    await service.search_facts(TrustedMemoryContext(user_id="user-1"), query="q", limit=999)

    search.assert_awaited_once_with(user_id="user-1", query="q", limit=MAX_SEARCH_LIMIT)


async def test_default_vector_floor_is_applied_when_not_specified():
    hits = (MemoryFactHit(fact_id="f1", content="x", score=DEFAULT_VECTOR_FLOOR - 0.01),)
    search = AsyncMock(return_value=hits)
    service = _service(search=search)

    result = await service.search_facts(TrustedMemoryContext(user_id="user-1"), query="q")

    assert result == ()


async def test_hybrid_search_filters_out_borderline_irrelevant_query():
    # Below the vector floor and matched by no keyword: reached by neither signal.
    hits = (MemoryFactHit(fact_id="f1", content="Ben 2004 doğumluyum", score=0.5219),)
    search = AsyncMock(return_value=hits)
    service = _service(search=search)

    result = await service.search_facts(
        TrustedMemoryContext(user_id="user-1"),
        query="hangi türden romanları sevdiğimi bilir misin?",
    )

    assert result == ()


async def test_hybrid_search_retains_relevant_query_with_lexical_overlap():
    # Below the vector floor, but the lexical signal reaches it on its own.
    hits = (MemoryFactHit(fact_id="f1", content="Ben 2004 doğumluyum", score=0.6586),)
    search = AsyncMock(return_value=hits)
    service = _service(search=search)

    result = await service.search_facts(
        TrustedMemoryContext(user_id="user-1"),
        query="doğum tarihim hakkında bilgin var mıdır?",
    )

    assert len(result) == 1
    assert result[0].fact_id == "f1"
    assert result[0].score > 0.0
    assert result[0].vector_score == 0.6586
    assert result[0].bm25_score > 0.0
