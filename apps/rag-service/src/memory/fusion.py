"""Weighted Reciprocal Rank Fusion for user memory fact retrieval.

Combines the dense vector ranking (semantic intent) with the Turkish-aware
BM25 ranking (exact and inflected keyword evidence) using the same weighted
RRF that ``graph.service.hybrid_search`` applies to its own Lucene BM25 and
vector signals -- ``weight / (k + rank + 1)``, k=60, summed per candidate.
One service answering "how do we merge a lexical and a dense ranking" two
different ways was an inconsistency, not a design.

Ranks rather than scores, because cosine and BM25 do not share a scale. The
previous weighted sum of raw scores, gated by an absolute threshold on the
blended value, only held while both signals stayed in the range it was tuned
against: measured on Turkish facts, relevant hits scored ~0.65-0.69 cosine
against an effective 0.714 bar, so the lexical term was load-bearing and a
change of embedding model would have quietly turned recall off. BM25 scores
were also max-normalised across candidates, which gave the best candidate
exactly 1.0 whenever any overlap existed -- a presence flag, not a relevance
score.

The relevance decision moved with it. Milvus returns its nearest k however
far away they are, so something has to keep an off-topic turn from recalling
five unrelated facts; that is now a floor on the dense signal alone, where
the number is interpretable, instead of on a blended value where it was not.
A lexical hit stands on its own and is not subject to it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.memory.contract import MemoryFactHit

#: Mirrors graph.service.hybrid_search's vector_weight/graph_weight split.
DEFAULT_VECTOR_WEIGHT = 0.40
DEFAULT_LEXICAL_WEIGHT = 0.60

#: Standard RRF damping constant, as used by graph.service.hybrid_search and
#: by Elasticsearch/Milvus/Weaviate defaults.
RRF_K = 60

#: Minimum cosine similarity for a fact to count as a dense-signal candidate.
#: Calibrated against nomic-embed-text (the configured OLLAMA_EMBED_MODEL) on
#: Turkish facts, where relevant hits sit around 0.69-0.92 and unrelated
#: neighbours around 0.54-0.78: at this value an off-topic turn recalls no
#: more than the previous threshold did, while on-topic recall improves.
#: It is a property of the embedding model, so it needs re-checking if that
#: model changes.
DEFAULT_VECTOR_FLOOR = 0.70


def fuse_hybrid_scores(
    hits: Sequence[MemoryFactHit],
    bm25_scores: Sequence[float],
    *,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
    rrf_k: int = RRF_K,
    vector_floor: float = DEFAULT_VECTOR_FLOOR,
) -> tuple[MemoryFactHit, ...]:
    """Fuse the dense and lexical rankings of one candidate set.

    Args:
        hits: Candidates from the vector search, carrying their cosine score.
        bm25_scores: Raw (un-normalised) BM25 scores, positionally aligned
            with `hits`. Only their order matters.
        vector_weight: Weight of the dense ranking's RRF contribution.
        lexical_weight: Weight of the BM25 ranking's RRF contribution.
        rrf_k: RRF damping constant; larger values flatten rank differences.
        vector_floor: Minimum cosine for a candidate to enter the dense
            ranking. The lexical ranking is not subject to it.

    Returns:
        Candidates reached by at least one signal, best first. A candidate
        below `vector_floor` that no keyword matched is reached by neither
        and is dropped.
    """
    if not hits:
        return ()

    from src.memory.contract import MemoryFactHit

    paired = list(zip(hits, bm25_scores, strict=False))
    fused_scores: dict[str, float] = {}

    # Dense signal, best cosine first. Milvus already returns them in that
    # order; sorting again keeps this correct if a caller ever does not.
    dense_ranked = sorted(
        (pair for pair in paired if pair[0].score >= vector_floor),
        key=lambda pair: pair[0].score,
        reverse=True,
    )
    for rank, (hit, _) in enumerate(dense_ranked):
        fused_scores[hit.fact_id] = fused_scores.get(hit.fact_id, 0.0) + vector_weight / (rrf_k + rank + 1)

    # Lexical signal, best BM25 first. A zero score is no evidence at all,
    # so those candidates are not ranked rather than ranked last.
    lexical_ranked = sorted(
        (pair for pair in paired if pair[1] > 0.0),
        key=lambda pair: pair[1],
        reverse=True,
    )
    for rank, (hit, _) in enumerate(lexical_ranked):
        fused_scores[hit.fact_id] = fused_scores.get(hit.fact_id, 0.0) + lexical_weight / (rrf_k + rank + 1)

    fused_hits = [
        MemoryFactHit(
            fact_id=hit.fact_id,
            content=hit.content,
            score=round(fused_scores[hit.fact_id], 6),
            vector_score=round(hit.score, 4),
            bm25_score=round(bm25_score, 4),
        )
        for hit, bm25_score in paired
        if hit.fact_id in fused_scores
    ]
    fused_hits.sort(key=lambda hit: hit.score, reverse=True)
    return tuple(fused_hits)
