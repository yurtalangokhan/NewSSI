"""Unit tests for memory hybrid fusion (src.memory.fusion).

Fusion is weighted Reciprocal Rank Fusion, the same scheme
``graph.service.hybrid_search`` already uses to combine its Lucene BM25 and
vector signals -- one service should not carry two different answers to
"how do we merge a lexical and a dense ranking".

It replaces a weighted sum of raw scores gated by an absolute threshold on
the blended value. That scheme had two defects. Cosine and BM25 do not share
a scale, so the sum was only meaningful while both stayed in the range it was
tuned against: measured on Turkish facts, relevant hits scored ~0.65-0.69
cosine against a 0.714 effective bar, so the lexical bonus was load-bearing
and a change of embedding model would silently return nothing. And BM25
scores were max-normalised across the candidates, which handed the best
candidate exactly 1.0 whenever any lexical overlap existed at all -- a
presence flag dressed up as a relevance score.

Ranks carry neither problem: they are invariant to the scale of either
signal.
"""

from __future__ import annotations

from src.memory.contract import MemoryFactHit
from src.memory.fusion import (
    DEFAULT_LEXICAL_WEIGHT,
    DEFAULT_VECTOR_FLOOR,
    DEFAULT_VECTOR_WEIGHT,
    RRF_K,
    fuse_hybrid_scores,
)


def test_uses_the_same_rrf_constants_as_graph_hybrid_search() -> None:
    assert (DEFAULT_VECTOR_WEIGHT, DEFAULT_LEXICAL_WEIGHT) == (0.4, 0.6)
    assert RRF_K == 60


def test_lexical_match_outranks_a_higher_cosine_without_one() -> None:
    hits = [
        MemoryFactHit(fact_id="f1", content="Kullanıcı 2004 doğumludur.", score=0.72),
        MemoryFactHit(fact_id="f2", content="Kullanıcı Kayseri'de yaşıyor.", score=0.78),
    ]

    fused = fuse_hybrid_scores(hits, [3.4, 0.0])

    assert [h.fact_id for h in fused] == ["f1", "f2"]


def test_ranking_is_unchanged_when_every_vector_score_shifts() -> None:
    """The property the weighted sum did not have.

    A new embedding model moves the whole cosine range; with ranks that
    cannot reorder anything, so recall does not quietly change behaviour.
    """
    contents = ["Kullanıcı Python kullanır.", "Kullanıcı İzmir'de doğdu."]
    bm25 = [2.0, 0.5]

    high = fuse_hybrid_scores(
        [
            MemoryFactHit(fact_id="f1", content=contents[0], score=0.91),
            MemoryFactHit(fact_id="f2", content=contents[1], score=0.88),
        ],
        bm25,
    )
    low = fuse_hybrid_scores(
        [
            MemoryFactHit(fact_id="f1", content=contents[0], score=0.76),
            MemoryFactHit(fact_id="f2", content=contents[1], score=0.73),
        ],
        bm25,
    )

    assert [h.fact_id for h in high] == [h.fact_id for h in low]


def test_candidate_below_the_vector_floor_without_a_lexical_match_is_dropped() -> None:
    hits = [MemoryFactHit(fact_id="f1", content="Kullanıcı kahve sever.", score=0.55)]

    fused = fuse_hybrid_scores(hits, [0.0])

    assert fused == ()


def test_candidate_below_the_vector_floor_is_still_rescued_by_a_lexical_match() -> None:
    """Milvus always returns its nearest k, however far away they are, so the
    floor is what keeps an off-topic turn from recalling anything. It applies
    to the dense signal alone: an exact keyword hit is evidence in its own
    right and does not need the dense branch's permission.
    """
    hits = [MemoryFactHit(fact_id="f1", content="Kullanıcı 2004 doğumludur.", score=0.55)]

    fused = fuse_hybrid_scores(hits, [4.1])

    assert [h.fact_id for h in fused] == ["f1"]


def test_a_hit_found_by_both_signals_outranks_one_found_by_either_alone() -> None:
    hits = [
        MemoryFactHit(fact_id="only_vector", content="Kullanıcı yoga yapar.", score=0.80),
        MemoryFactHit(fact_id="both", content="Kullanıcı Python kullanır.", score=0.79),
    ]

    fused = fuse_hybrid_scores(hits, [0.0, 2.5])

    assert fused[0].fact_id == "both"


def test_component_scores_are_reported_alongside_the_fused_score() -> None:
    hits = [MemoryFactHit(fact_id="f1", content="Kullanıcı Python kullanır.", score=0.81)]

    fused = fuse_hybrid_scores(hits, [2.5])

    assert fused[0].vector_score == 0.81
    assert fused[0].bm25_score == 2.5
    assert fused[0].score > 0.0


def test_default_vector_floor_is_calibrated_and_documented() -> None:
    assert DEFAULT_VECTOR_FLOOR == 0.70


def test_empty_hits_returns_empty_tuple() -> None:
    assert fuse_hybrid_scores([], []) == ()
