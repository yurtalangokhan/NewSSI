"""Data Operations — the Table family (12 operations).

Langflow calls its `DataFrame` type "Table" in the UI. Every body here is
ported from `OperationsComponent`'s pandas calls, so the expectations are
about pandas' real behaviour, not a paraphrase of the operation name.
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.flows.data_ops import TABLE_OPERATIONS, run_table_operation


def _df(**columns) -> pd.DataFrame:
    return pd.DataFrame(columns)


def _run(operation, frames, **values):
    if isinstance(frames, pd.DataFrame):
        frames = [frames]
    return run_table_operation(operation, frames, values)


def test_the_family_has_langflows_twelve_operations():
    assert TABLE_OPERATIONS == {
        "Add Column",
        "Concatenate",
        "Drop Column",
        "Filter",
        "Head",
        "Merge",
        "Rename Column",
        "Replace Value",
        "Select Columns",
        "Sort",
        "Tail",
        "Drop Duplicates",
    }


# ---------------------------------------------------------------------------
# Filter — eight operators
# ---------------------------------------------------------------------------

FILTER_TABLE = {"ad": ["ali", "ayse", "veli"], "puan": [10, 5, 20]}


@pytest.mark.parametrize(
    ("operator", "value", "column", "expected"),
    [
        ("equals", "ali", "ad", ["ali"]),
        ("not equals", "ali", "ad", ["ayse", "veli"]),
        ("contains", "li", "ad", ["ali", "veli"]),
        ("not contains", "li", "ad", ["ayse"]),
        ("starts with", "a", "ad", ["ali", "ayse"]),
        ("ends with", "i", "ad", ["ali", "veli"]),
    ],
)
def test_filter_string_operators(operator, value, column, expected):
    out = _run(
        "Filter",
        _df(**FILTER_TABLE),
        column_name=column,
        filter_value=value,
        filter_operator=operator,
    )
    assert list(out["ad"]) == expected


def test_filter_greater_and_less_than_compare_numerically():
    out = _run(
        "Filter",
        _df(**FILTER_TABLE),
        column_name="puan",
        filter_value="9",
        filter_operator="greater than",
    )
    assert sorted(out["puan"]) == [10, 20]


def test_filter_falls_back_to_a_string_comparison_for_a_non_numeric_value():
    """Langflow catches the numeric coercion failure and compares as text."""
    out = _run(
        "Filter",
        _df(ad=["b", "a"]),
        column_name="ad",
        filter_value="a",
        filter_operator="greater than",
    )
    assert list(out["ad"]) == ["b"]


def test_an_unknown_filter_operator_falls_back_to_equality():
    out = _run(
        "Filter",
        _df(**FILTER_TABLE),
        column_name="ad",
        filter_value="ali",
        filter_operator="bilinmeyen",
    )
    assert list(out["ad"]) == ["ali"]


# ---------------------------------------------------------------------------
# Column operations
# ---------------------------------------------------------------------------


def test_sort_orders_by_a_column_in_either_direction():
    out = _run("Sort", _df(**FILTER_TABLE), column_name="puan", ascending=True)
    assert list(out["puan"]) == [5, 10, 20]
    out = _run("Sort", _df(**FILTER_TABLE), column_name="puan", ascending=False)
    assert list(out["puan"]) == [20, 10, 5]


def test_drop_column_removes_it():
    out = _run("Drop Column", _df(**FILTER_TABLE), column_name="puan")
    assert list(out.columns) == ["ad"]


def test_rename_column_renames_it():
    out = _run("Rename Column", _df(**FILTER_TABLE), column_name="puan", new_column_name="skor")
    assert list(out.columns) == ["ad", "skor"]


def test_add_column_fills_every_row_with_one_value():
    out = _run("Add Column", _df(**FILTER_TABLE), new_column_name="ulke", new_column_value="TR")
    assert list(out["ulke"]) == ["TR", "TR", "TR"]


def test_select_columns_keeps_the_named_ones_and_trims_whitespace():
    out = _run("Select Columns", _df(**FILTER_TABLE), columns_to_select=[" puan "])
    assert list(out.columns) == ["puan"]


def test_head_and_tail_take_the_first_and_last_rows():
    assert list(_run("Head", _df(**FILTER_TABLE), num_rows=2)["ad"]) == ["ali", "ayse"]
    assert list(_run("Tail", _df(**FILTER_TABLE), num_rows=2)["ad"]) == ["ayse", "veli"]


def test_replace_value_swaps_a_value_inside_one_column():
    out = _run(
        "Replace Value",
        _df(**FILTER_TABLE),
        column_name="ad",
        replace_value="ali",
        replacement_value="ALI",
    )
    assert list(out["ad"]) == ["ALI", "ayse", "veli"]


def test_drop_duplicates_uses_the_named_column_as_the_subset():
    out = _run("Drop Duplicates", _df(ad=["ali", "ali", "veli"], n=[1, 2, 3]), column_name="ad")
    assert list(out["ad"]) == ["ali", "veli"]
    assert list(out["n"]) == [1, 3]


def test_an_operation_does_not_mutate_the_input_table():
    """Langflow copies the frame first; a node that edited its input in place
    would corrupt whatever else read the same value out of scratch."""
    original = _df(**FILTER_TABLE)
    _run("Add Column", original, new_column_name="yeni", new_column_value=1)
    assert "yeni" not in original.columns


# ---------------------------------------------------------------------------
# Concatenate / Merge — the two that take several tables
# ---------------------------------------------------------------------------


def test_concatenate_stacks_rows_and_renumbers_the_index():
    out = run_table_operation("Concatenate", [_df(ad=["ali"]), _df(ad=["veli"])], {})
    assert list(out["ad"]) == ["ali", "veli"]
    assert list(out.index) == [0, 1]


def test_concatenate_of_one_table_returns_it():
    out = run_table_operation("Concatenate", [_df(ad=["ali"])], {})
    assert list(out["ad"]) == ["ali"]


def test_merge_joins_on_a_shared_column():
    left = _df(id=[1, 2], ad=["ali", "ayse"])
    right = _df(id=[1, 2], puan=[10, 20])
    out = run_table_operation(
        "Merge",
        [],
        {
            "left_dataframe": left,
            "right_dataframe": right,
            "merge_on_column": "id",
            "merge_how": "inner",
        },
    )
    assert sorted(out.columns) == ["ad", "id", "puan"]
    assert len(out) == 2


def test_merge_folds_an_overlapping_column_back_instead_of_leaving_a_suffix():
    """Langflow merges with suffixes ("", "_right"), then combine_first's the
    `_right` column back into the original and drops it."""
    left = _df(id=[1, 2], ad=["ali", None])
    right = _df(id=[1, 2], ad=["X", "ayse"])
    out = run_table_operation(
        "Merge",
        [],
        {
            "left_dataframe": left,
            "right_dataframe": right,
            "merge_on_column": "id",
            "merge_how": "inner",
        },
    )
    assert "ad_right" not in out.columns
    assert list(out["ad"]) == ["ali", "ayse"]


def test_merge_rejects_a_column_missing_from_either_side():
    left, right = _df(id=[1]), _df(other=[1])
    with pytest.raises(ValueError, match="not found"):
        run_table_operation(
            "Merge",
            [],
            {
                "left_dataframe": left,
                "right_dataframe": right,
                "merge_on_column": "id",
                "merge_how": "inner",
            },
        )


def test_merge_without_a_column_joins_on_the_index():
    left = _df(ad=["ali", "ayse"])
    right = _df(puan=[10, 20])
    out = run_table_operation(
        "Merge",
        [],
        {
            "left_dataframe": left,
            "right_dataframe": right,
            "merge_on_column": "",
            "merge_how": "inner",
        },
    )
    assert sorted(out.columns) == ["ad", "puan"]


def test_merge_without_a_right_table_returns_the_left_one():
    left = _df(ad=["ali"])
    out = run_table_operation("Merge", [], {"left_dataframe": left})
    assert list(out["ad"]) == ["ali"]


def test_an_unknown_table_operation_is_rejected():
    with pytest.raises(ValueError, match="Unsupported operation"):
        _run("Yok Böyle", _df(**FILTER_TABLE))
