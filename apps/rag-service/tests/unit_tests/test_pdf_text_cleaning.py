"""``clean_pdf_text`` reconstructs bullet lists and soft line breaks from raw
PDF text extraction, which otherwise hard-wraps every line at the page
width and separates each bullet glyph from its text onto its own line.
Previously untested despite being real, easy-to-break heuristic logic.
"""

from __future__ import annotations

from src.documents.processor import (
    _is_standalone_bullet,
    _should_join_lines,
    clean_pdf_text,
)

# ---------------------------------------------------------------------------
# _is_standalone_bullet
# ---------------------------------------------------------------------------


def test_bullet_glyph_alone_is_a_standalone_bullet():
    assert _is_standalone_bullet("•") is True


def test_numbered_marker_is_a_standalone_bullet():
    assert _is_standalone_bullet("1.") is True


def test_lettered_marker_is_a_standalone_bullet():
    assert _is_standalone_bullet("a)") is True


def test_parenthesized_marker_needs_a_trailing_punctuation_mark():
    # The marker group `\([0-9a-zA-Z]+\)` already consumes the parens, so a
    # bare "(1)" does not match -- the regex still requires one more
    # trailing "." or ")" after that group.
    assert _is_standalone_bullet("(1)") is False
    assert _is_standalone_bullet("(1).") is True


def test_plain_word_is_not_a_standalone_bullet():
    assert _is_standalone_bullet("hello") is False


# ---------------------------------------------------------------------------
# _should_join_lines
# ---------------------------------------------------------------------------


def test_join_when_previous_line_ends_with_a_soft_continuation_mark():
    assert _should_join_lines("ends with comma,", "next") is True
    assert _should_join_lines("ends with dash-", "next") is True


def test_no_join_when_previous_line_ends_a_sentence():
    for terminator in (".", "!", "?", ":", ";"):
        assert _should_join_lines(f"a sentence{terminator}", "next") is False


def test_no_join_into_a_numbered_list_item():
    assert _should_join_lines("no terminal punctuation here", "1. numbered") is False


def test_join_when_continuation_starts_lowercase():
    assert _should_join_lines("no terminal punctuation here", "wraps onward") is True


def test_no_join_when_continuation_starts_uppercase():
    assert _should_join_lines("no terminal punctuation here", "Capitalized") is False


def test_no_join_when_either_side_is_empty():
    assert _should_join_lines("", "x") is False
    assert _should_join_lines("x", "") is False


# ---------------------------------------------------------------------------
# clean_pdf_text
# ---------------------------------------------------------------------------


def test_empty_text_returns_empty_string():
    assert clean_pdf_text("") == ""


def test_sentence_ending_lines_stay_on_separate_lines():
    text = "Hello world.\nNext sentence."
    assert clean_pdf_text(text) == text


def test_soft_wrapped_paragraph_is_rejoined_into_one_line():
    text = "This is a long sentence that\nwraps onto the next line."
    assert clean_pdf_text(text) == (
        "This is a long sentence that wraps onto the next line."
    )


def test_comma_continuation_is_rejoined():
    text = "The items are,\napples and oranges."
    assert clean_pdf_text(text) == "The items are, apples and oranges."


def test_a_numbered_list_item_is_never_merged_into_the_preceding_line():
    text = "This is text\n1. First item"
    assert clean_pdf_text(text) == text


def test_bullet_glyph_and_text_on_separate_lines_are_reconstructed():
    text = "•\nFirst item\n•\nSecond item"
    assert clean_pdf_text(text) == "• First item\n• Second item"


def test_bullet_glyph_already_on_the_same_line_as_its_text_is_preserved():
    text = "• First item\n• Second item"
    assert clean_pdf_text(text) == text


def test_runs_of_blank_lines_collapse_to_a_single_blank_line():
    text = "Para one.\n\n\n\nPara two."
    assert clean_pdf_text(text) == "Para one.\n\nPara two."
