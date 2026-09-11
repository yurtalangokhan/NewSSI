"""Parser — Langflow's "extract text using a template".

Two modes, and the asymmetry between them is Langflow's own: over a table the
template uses `str.format(**row)`, which raises on a missing column; over JSON
it uses `format_map` with a defaulting dict, which quietly substitutes an empty
string. Both are pinned here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.flows.data_ops import parse_with_template, stringify_value

ROWS = pd.DataFrame({"ad": ["ali", "veli"], "puan": [10, 20]})


# ---------------------------------------------------------------------------
# Parser mode
# ---------------------------------------------------------------------------


def test_a_table_is_rendered_one_row_per_line():
    out = parse_with_template(ROWS, "{ad}: {puan}", "\n")
    assert out == "ali: 10\nveli: 20"


def test_the_separator_is_used_between_rows():
    assert parse_with_template(ROWS, "{ad}", " | ") == "ali | veli"


def test_a_json_object_is_rendered_once():
    assert parse_with_template({"ad": "ali"}, "Merhaba {ad}", "\n") == "Merhaba ali"


def test_a_list_of_objects_is_rendered_per_item():
    out = parse_with_template([{"ad": "ali"}, {"ad": "veli"}], "{ad}", "\n")
    assert out == "ali\nveli"


def test_a_missing_key_over_json_becomes_an_empty_string():
    """Langflow's `_DefaultDict.__missing__`: the template still renders."""
    assert parse_with_template({"ad": "ali"}, "{ad}-{yok}", "\n") == "ali-"


def test_a_missing_column_over_a_table_raises():
    """The other half of Langflow's asymmetry: `format(**row)` has no default."""
    with pytest.raises(KeyError):
        parse_with_template(ROWS, "{yok}", "\n")


def test_an_empty_table_renders_nothing():
    assert parse_with_template(pd.DataFrame({"ad": []}), "{ad}", "\n") == ""


def test_an_unsupported_input_is_rejected_clearly():
    with pytest.raises(ValueError, match="Unsupported input"):
        parse_with_template(42, "{ad}", "\n")


# ---------------------------------------------------------------------------
# Stringify mode
# ---------------------------------------------------------------------------


def test_a_table_stringifies_to_a_markdown_table():
    out = stringify_value(ROWS)
    assert "| ad" in out and "ali" in out and "---" in out


def test_a_json_object_stringifies_to_a_fenced_json_block():
    out = stringify_value({"ad": "ali"})
    assert out.startswith("```json")
    assert '"ad": "ali"' in out
    assert out.endswith("```")


def test_text_is_cleaned_of_blank_lines_and_long_runs():
    """Langflow's `clean_string`: blank lines emptied, 3+ newlines collapsed."""
    assert stringify_value("a\n\n\n\nb") == "a\n\nb"


def test_clean_data_drops_empty_rows_from_a_table():
    frame = pd.DataFrame({"ad": ["ali", None], "puan": [10, None]})
    assert "ali" in stringify_value(frame, clean_data=True)
    assert stringify_value(frame, clean_data=True).count("nan") == 0


def test_a_list_stringifies_one_item_per_line():
    out = stringify_value([{"a": 1}, {"a": 2}])
    assert out.count("```json") == 2
