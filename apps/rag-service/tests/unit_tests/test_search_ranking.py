from __future__ import annotations

import pytest

from src.search.ranking import RRF_K, FusedItem, fuse_ranked_lists


def test_empty_input_fuses_to_nothing() -> None:
    assert fuse_ranked_lists([], key=str) == []
    assert fuse_ranked_lists([[], []], key=str) == []


def test_single_list_keeps_order_and_scales_relevance_to_top_hit() -> None:
    fused = fuse_ranked_lists([["a", "b", "c"]], key=str)

    assert [item.item for item in fused] == ["a", "b", "c"]
    assert fused[0].relevance == 1.0
    assert fused[1].relevance == pytest.approx((RRF_K + 1) / (RRF_K + 2), abs=1e-4)
    assert fused[0].score == pytest.approx(1 / (RRF_K + 1))


def test_equal_ranks_alternate_in_list_order() -> None:
    documents = ["d1", "d2", "d3"]
    entities = ["e1", "e2"]

    fused = fuse_ranked_lists([documents, entities], key=str)

    assert [item.item for item in fused] == ["d1", "e1", "d2", "e2", "d3"]


def test_items_found_by_several_lists_accumulate_score() -> None:
    fused = fuse_ranked_lists([["x", "shared"], ["shared", "y"]], key=str)

    assert fused[0].item == "shared"
    assert fused[0].score == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert [item.item for item in fused[1:]] == ["x", "y"]


def test_first_occurrence_wins_for_duplicate_keys() -> None:
    first = {"id": 1, "v": "first"}
    second = {"id": 1, "v": "second"}

    fused = fuse_ranked_lists([[first], [second]], key=lambda row: row["id"])

    assert fused == [
        FusedItem(item=first, score=pytest.approx(2 / (RRF_K + 1)), relevance=1.0)
    ]


def test_custom_k_changes_score_spread() -> None:
    fused = fuse_ranked_lists([["a", "b"]], key=str, k=0)

    assert fused[1].relevance == 0.5
