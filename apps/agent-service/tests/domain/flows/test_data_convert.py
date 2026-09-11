"""Type Convert and Split Text — Langflow's two standalone processing nodes.

Langflow's vocabulary again: `Data` is shown as **JSON**, `DataFrame` as
**Table**. `convert_value` is its `convert_to_message` / `convert_to_data` /
`convert_to_dataframe` trio behind one call.
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.flows.data_ops import convert_value, split_text

# ---------------------------------------------------------------------------
# Type Convert — to Message
# ---------------------------------------------------------------------------


def test_text_to_message_is_the_text():
    assert convert_value("merhaba", "Message") == "merhaba"


def test_json_to_message_renders_the_object():
    assert convert_value({"a": 1}, "Message") == "{'a': 1}"


def test_a_table_to_message_renders_the_table():
    out = convert_value(pd.DataFrame({"a": [1]}), "Message")
    assert "a" in out and "1" in out


# ---------------------------------------------------------------------------
# Type Convert — to JSON
# ---------------------------------------------------------------------------


def test_text_to_json_wraps_it_under_text():
    assert convert_value("merhaba", "JSON") == {"text": "merhaba"}


def test_json_stays_json():
    assert convert_value({"a": 1}, "JSON") == {"a": 1}


def test_a_table_to_json_becomes_records():
    out = convert_value(pd.DataFrame({"a": [1, 2]}), "JSON")
    assert out == {"records": [{"a": 1}, {"a": 2}]}


def test_auto_parse_reads_a_json_string_instead_of_wrapping_it():
    assert convert_value('{"a": 1}', "JSON", auto_parse=True) == {"a": 1}


def test_auto_parse_puts_a_json_array_under_records():
    assert convert_value('[{"a": 1}]', "JSON", auto_parse=True) == {"records": [{"a": 1}]}


def test_auto_parse_reads_a_csv_string():
    out = convert_value("a,b\n1,2\n3,4", "JSON", auto_parse=True)
    assert out == {"records": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}


def test_auto_parse_needs_more_than_a_header_to_call_something_csv():
    """Langflow's heuristic: at least two lines, and a comma in the header."""
    assert convert_value("a,b", "JSON", auto_parse=True) == {"text": "a,b"}


def test_auto_parse_leaves_prose_alone():
    assert convert_value("sadece bir cümle", "JSON", auto_parse=True) == {
        "text": "sadece bir cümle"
    }


def test_without_auto_parse_a_json_string_is_still_just_text():
    assert convert_value('{"a": 1}', "JSON") == {"text": '{"a": 1}'}


# ---------------------------------------------------------------------------
# Type Convert — to Table
# ---------------------------------------------------------------------------


def test_json_to_table_is_a_single_row():
    out = convert_value({"a": 1, "b": 2}, "Table")
    assert list(out.columns) == ["a", "b"]
    assert len(out) == 1


def test_a_single_key_holding_a_list_of_objects_opens_into_real_rows():
    """Langflow's `Data.to_dataframe`: one key whose value is a list of dicts
    becomes the table itself, not a one-row frame holding a list."""
    out = convert_value({"records": [{"a": 1}, {"a": 2}]}, "Table")
    assert list(out["a"]) == [1, 2]


def test_a_table_stays_a_table():
    frame = pd.DataFrame({"a": [1]})
    assert convert_value(frame, "Table") is frame


def test_a_list_of_objects_becomes_rows():
    out = convert_value([{"a": 1}, {"a": 2}], "Table")
    assert list(out["a"]) == [1, 2]


def test_auto_parse_turns_a_csv_string_into_a_real_table():
    out = convert_value("a,b\n1,2\n3,4", "Table", auto_parse=True)
    assert list(out.columns) == ["a", "b"]
    assert list(out["a"]) == [1, 3]


def test_an_unknown_output_type_is_rejected():
    with pytest.raises(ValueError, match="Unsupported output type"):
        convert_value("x", "Yok")


# ---------------------------------------------------------------------------
# Split Text
# ---------------------------------------------------------------------------


def test_split_text_chunks_on_the_separator():
    out = split_text("bir\niki\nuc", {"chunk_size": 4, "chunk_overlap": 0, "separator": "\n"})
    assert list(out["text"]) == ["bir", "iki", "uc"]


def test_split_text_merges_pieces_up_to_the_chunk_size():
    out = split_text("bir\niki\nuc", {"chunk_size": 100, "chunk_overlap": 0, "separator": "\n"})
    assert len(out) == 1


def test_a_slash_n_separator_is_read_as_a_newline():
    """Langflow's `_fix_separator` fixes this common typo before splitting."""
    out = split_text("bir\niki", {"chunk_size": 4, "chunk_overlap": 0, "separator": "/n"})
    assert list(out["text"]) == ["bir", "iki"]


def test_an_escaped_newline_is_unescaped_too():
    out = split_text("bir\niki", {"chunk_size": 4, "chunk_overlap": 0, "separator": "\\n"})
    assert list(out["text"]) == ["bir", "iki"]


def test_split_text_of_empty_input_is_rejected():
    with pytest.raises(TypeError, match="No data inputs"):
        split_text("", {"chunk_size": 10, "chunk_overlap": 0, "separator": "\n"})


def test_keep_separator_accepts_langflows_string_form():
    out = split_text(
        "bir\niki",
        {"chunk_size": 4, "chunk_overlap": 0, "separator": "\n", "keep_separator": "False"},
    )
    assert list(out["text"]) == ["bir", "iki"]


def test_split_text_can_take_a_table_and_split_its_text_column():
    frame = pd.DataFrame({"text": ["bir\niki"]})
    out = split_text(
        frame, {"chunk_size": 4, "chunk_overlap": 0, "separator": "\n", "text_key": "text"}
    )
    assert list(out["text"]) == ["bir", "iki"]
