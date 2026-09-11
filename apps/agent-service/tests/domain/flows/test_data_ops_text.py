"""Data Operations — the Text family (10 operations).

Two of these are Text operations that do not produce text, which is Langflow's
own routing and not a slip here: `Word Count` outputs JSON and
`Text to DataFrame` outputs a table.
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.flows.data_ops import (
    DATA_OUTPUT_OPERATIONS,
    DATAFRAME_OUTPUT_OPERATIONS,
    MESSAGE_OUTPUT_OPERATIONS,
    TEXT_OPERATIONS,
    format_result_as_text,
    run_text_operation,
)


def _run(operation, text, **values):
    return run_text_operation(operation, text, values)


def test_the_family_has_langflows_ten_operations():
    assert TEXT_OPERATIONS == {
        "Word Count",
        "Case Conversion",
        "Text Replace",
        "Text Extract",
        "Text Head",
        "Text Tail",
        "Text Strip",
        "Text Join",
        "Text Clean",
        "Text to DataFrame",
    }


def test_two_text_operations_deliberately_leave_the_text_family_output():
    """Langflow's `as_data` handles Word Count and `as_dataframe` handles Text
    to DataFrame, even though both sit under the Text picker."""
    assert "Word Count" in DATA_OUTPUT_OPERATIONS
    assert "Text to DataFrame" in DATAFRAME_OUTPUT_OPERATIONS
    assert "Word Count" not in MESSAGE_OUTPUT_OPERATIONS
    assert "Text to DataFrame" not in MESSAGE_OUTPUT_OPERATIONS


# ---------------------------------------------------------------------------
# Word Count
# ---------------------------------------------------------------------------


def test_word_count_reports_words_characters_and_lines():
    result = _run(
        "Word Count",
        "bir iki\nbir",
        count_words=True,
        count_characters=True,
        count_lines=True,
    )
    assert result["word_count"] == 3
    assert result["unique_words"] == 2
    assert result["character_count"] == len("bir iki\nbir")
    assert result["character_count_no_spaces"] == len("bir iki\nbir".replace(" ", ""))
    assert result["line_count"] == 2
    assert result["non_empty_lines"] == 2


def test_word_count_omits_a_group_that_is_switched_off():
    result = _run(
        "Word Count", "bir iki", count_words=True, count_characters=False, count_lines=False
    )
    assert "word_count" in result
    assert "character_count" not in result
    assert "line_count" not in result


def test_word_count_of_blank_text_is_zeroes_not_an_empty_result():
    result = _run("Word Count", "   ", count_words=True, count_characters=True, count_lines=True)
    assert result["word_count"] == 0
    assert result["character_count"] == 0
    assert result["line_count"] == 0


# ---------------------------------------------------------------------------
# Case Conversion / Replace / Extract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_type", "expected"),
    [
        ("uppercase", "MERHABA DUNYA"),
        ("lowercase", "merhaba dunya"),
        ("title", "Merhaba Dunya"),
        ("capitalize", "Merhaba dunya"),
        ("swapcase", "mERHABA dUNYA"),
    ],
)
def test_case_conversion_covers_langflows_five_modes(case_type, expected):
    assert _run("Case Conversion", "Merhaba Dunya", case_type=case_type) == expected


def test_an_unknown_case_type_leaves_the_text_alone():
    assert _run("Case Conversion", "Merhaba", case_type="yok") == "Merhaba"


def test_text_replace_is_literal_unless_regex_is_switched_on():
    assert _run("Text Replace", "a.b.c", search_pattern=".", replacement_text="-") == "a-b-c"
    assert (
        _run("Text Replace", "a.b.c", search_pattern=".", replacement_text="-", use_regex=True)
        == "-----"
    )


def test_text_replace_keeps_the_text_when_the_regex_is_invalid():
    """Langflow logs and returns the input rather than failing the run."""
    assert (
        _run("Text Replace", "abc", search_pattern="[", replacement_text="-", use_regex=True)
        == "abc"
    )


def test_text_replace_without_a_pattern_is_a_no_op():
    assert _run("Text Replace", "abc", search_pattern="") == "abc"


def test_text_extract_returns_the_matches_up_to_the_limit():
    assert _run("Text Extract", "a1b2c3", extract_pattern=r"\d", max_matches=2) == ["1", "2"]


def test_text_extract_with_a_zero_limit_returns_every_match():
    assert _run("Text Extract", "a1b2c3", extract_pattern=r"\d", max_matches=0) == ["1", "2", "3"]


def test_text_extract_raises_on_an_invalid_pattern():
    """Unlike Text Replace, this one refuses — Langflow's own asymmetry."""
    with pytest.raises(ValueError, match="Invalid regex"):
        _run("Text Extract", "abc", extract_pattern="[", max_matches=5)


def test_text_extract_without_a_pattern_finds_nothing():
    assert _run("Text Extract", "abc", extract_pattern="") == []


# ---------------------------------------------------------------------------
# Head / Tail / Strip / Join / Clean
# ---------------------------------------------------------------------------


def test_text_head_and_tail_take_characters_from_each_end():
    assert _run("Text Head", "abcdef", head_characters=3) == "abc"
    assert _run("Text Tail", "abcdef", tail_characters=3) == "def"


def test_text_head_and_tail_of_zero_are_empty():
    assert _run("Text Head", "abcdef", head_characters=0) == ""
    assert _run("Text Tail", "abcdef", tail_characters=0) == ""


def test_a_negative_character_count_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        _run("Text Head", "abcdef", head_characters=-1)
    with pytest.raises(ValueError, match="non-negative"):
        _run("Text Tail", "abcdef", tail_characters=-1)


def test_text_strip_honours_the_mode_and_the_character_set():
    assert _run("Text Strip", "  ab  ", strip_mode="both") == "ab"
    assert _run("Text Strip", "  ab  ", strip_mode="left") == "ab  "
    assert _run("Text Strip", "  ab  ", strip_mode="right") == "  ab"
    assert _run("Text Strip", "xxabxx", strip_mode="both", strip_characters="x") == "ab"


def test_text_join_puts_a_newline_between_the_two_inputs():
    assert _run("Text Join", "bir", text_input_2="iki") == "bir\niki"


def test_text_join_returns_whichever_side_has_content():
    assert _run("Text Join", "", text_input_2="iki") == "iki"
    assert _run("Text Join", "bir", text_input_2="") == "bir"


def test_text_clean_collapses_spaces_but_keeps_newlines():
    """Langflow uses `[^\\S\\n]+` on purpose, so remove_empty_lines still has
    lines to work with when both options are on."""
    assert _run("Text Clean", "a   b\n\nc", remove_extra_spaces=True) == "a b\n\nc"


def test_text_clean_can_drop_special_characters_and_empty_lines():
    result = _run(
        "Text Clean",
        "a!!  b\n\nc",
        remove_extra_spaces=True,
        remove_special_chars=True,
        remove_empty_lines=True,
    )
    assert result == "a b\nc"


# ---------------------------------------------------------------------------
# Text to DataFrame
# ---------------------------------------------------------------------------


def test_text_to_dataframe_parses_a_pipe_table_with_a_header():
    out = _run(
        "Text to DataFrame",
        "| ad | puan |\n| ali | 10 |\n| veli | 20 |",
        table_separator="|",
        has_header=True,
    )
    assert list(out.columns) == ["ad", "puan"]
    assert list(out["ad"]) == ["ali", "veli"]


def test_text_to_dataframe_converts_numeric_columns():
    out = _run(
        "Text to DataFrame",
        "| ad | puan |\n| ali | 10 |",
        table_separator="|",
        has_header=True,
    )
    assert pd.api.types.is_numeric_dtype(out["puan"])


def test_text_to_dataframe_without_a_header_names_columns_positionally():
    out = _run("Text to DataFrame", "| ali | 10 |", table_separator="|", has_header=False)
    assert list(out.columns) == ["col_0", "col_1"]


def test_text_to_dataframe_rejects_a_row_that_does_not_match_the_header():
    with pytest.raises(ValueError, match="Header mismatch"):
        _run(
            "Text to DataFrame",
            "| a | b |\n| 1 |",
            table_separator="|",
            has_header=True,
        )


def test_text_to_dataframe_of_blank_text_is_an_empty_table():
    out = _run("Text to DataFrame", "   ", table_separator="|", has_header=True)
    assert out.empty


# ---------------------------------------------------------------------------
# Shared behaviour
# ---------------------------------------------------------------------------


def test_an_empty_input_yields_nothing_except_for_text_join():
    assert _run("Case Conversion", "", case_type="uppercase") is None
    assert _run("Text Join", "", text_input_2="iki") == "iki"


def test_a_list_result_is_rendered_one_item_per_line():
    assert format_result_as_text(["a", "b"]) == "a\nb"
    assert format_result_as_text(None) == ""
    assert format_result_as_text(5) == "5"
