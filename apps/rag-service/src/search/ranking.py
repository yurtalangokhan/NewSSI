"""Reciprocal Rank Fusion over per-collection, per-source ranked lists.

Store-native scores are not comparable across collections (Milvus defaults to
L2 distance, graph hits carry RRF scores), so only rank positions are fused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Sequence

RRF_K = 60
"""Standard RRF damping constant (Cormack et al., 2009)."""

T = TypeVar("T")


@dataclass(frozen=True)
class FusedItem(Generic[T]):
    """One fused item: its RRF score and its score relative to the best item."""

    item: T
    score: float
    relevance: float


@dataclass
class _Accumulator(Generic[T]):
    item: T
    score: float
    first_rank: int
    first_list: int


def fuse_ranked_lists(
    ranked_lists: Sequence[Sequence[T]],
    *,
    key: Callable[[T], Hashable],
    k: int = RRF_K,
) -> list[FusedItem[T]]:
    """Fuse ranked lists; equal scores keep rank-then-list order.

    The first occurrence of a key is the item kept; later occurrences only add
    to its score. ``relevance`` is the score divided by the best score.
    """
    accumulated: dict[Hashable, _Accumulator[T]] = {}
    for list_index, ranked in enumerate(ranked_lists):
        for rank, item in enumerate(ranked, start=1):
            contribution = 1.0 / (k + rank)
            identity = key(item)
            existing = accumulated.get(identity)
            if existing is None:
                accumulated[identity] = _Accumulator(
                    item=item,
                    score=contribution,
                    first_rank=rank,
                    first_list=list_index,
                )
            else:
                existing.score += contribution

    ordered = sorted(
        accumulated.values(),
        key=lambda entry: (-entry.score, entry.first_rank, entry.first_list),
    )
    if not ordered:
        return []
    best = ordered[0].score
    return [
        FusedItem(
            item=entry.item,
            score=entry.score,
            relevance=round(entry.score / best, 4),
        )
        for entry in ordered
    ]
