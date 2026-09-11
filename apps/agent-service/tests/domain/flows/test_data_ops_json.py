"""Data Operations — the JSON family (8 operations).

Every expectation here is read off Langflow's own `OperationsComponent`
bodies, not inferred from the operation name. Where Langflow does something
surprising — Select Keys' "data" special case, Path Selection swallowing its
error while JQ Expression raises — the surprise is the contract and is pinned
here on purpose.
"""

from __future__ import annotations

import pytest

from domain.flows.data_ops import JSON_OPERATIONS, run_json_operation


def _run(operation, data, **values):
    return run_json_operation(operation, data, values)


def test_the_family_has_langflows_eight_operations():
    assert JSON_OPERATIONS == {
        "Select Keys",
        "Literal Eval",
        "Combine",
        "Append or Update",
        "Remove Keys",
        "Rename Keys",
        "Path Selection",
        "JQ Expression",
    }


# ---------------------------------------------------------------------------
# Select Keys
# ---------------------------------------------------------------------------


def test_select_keys_keeps_only_the_named_top_level_keys():
    result = _run("Select Keys", {"a": 1, "b": 2, "c": 3}, select_keys_input=["a", "c"])
    assert result == {"a": 1, "c": 3}


def test_select_keys_with_the_single_key_data_unwraps_one_more_level():
    """Langflow's one special case, quirks included.

    `get_normalized_data()` already unwraps a `data` envelope, and select_keys
    then indexes `["data"]` on the *result* — so the case only fires on a
    doubly-wrapped payload. That is arguably a latent bug on their side, but
    the rule for this port is that the same name produces the same result, so
    it is mirrored rather than tidied.
    """
    result = _run("Select Keys", {"data": {"data": {"inner": 1}}}, select_keys_input=["data"])
    assert result == {"inner": 1}


def test_select_keys_named_data_on_a_singly_wrapped_payload_raises():
    """The other half of the same quirk, pinned so a future "fix" is a choice."""
    with pytest.raises(KeyError):
        _run("Select Keys", {"data": {"inner": 1}, "other": 2}, select_keys_input=["data"])


def test_select_keys_rejects_a_key_that_is_not_there():
    with pytest.raises(ValueError, match="not found"):
        _run("Select Keys", {"a": 1}, select_keys_input=["a", "yok"])


def test_select_keys_rejects_multiple_data_objects():
    with pytest.raises(ValueError, match="multiple data objects"):
        _run("Select Keys", [{"a": 1}, {"a": 2}], select_keys_input=["a"])


# ---------------------------------------------------------------------------
# Literal Eval
# ---------------------------------------------------------------------------


def test_literal_eval_parses_python_literals_recursively():
    result = _run("Literal Eval", {"a": "[1, 2]", "nested": {"b": "{'x': 1}"}})
    assert result == {"a": [1, 2], "nested": {"b": {"x": 1}}}


def test_literal_eval_leaves_plain_prose_alone():
    """Only strings that start like a literal, read as true/false/none, or are
    all digits once dots are removed, are even attempted."""
    result = _run("Literal Eval", {"a": "merhaba dünya", "b": "3.14"})
    assert result["a"] == "merhaba dünya"
    assert result["b"] == 3.14


def test_literal_eval_keeps_lowercase_true_as_a_string():
    """Langflow tries these — "true"/"false"/"none" pass its guard — but
    `ast.literal_eval` only knows Python's `True`/`False`/`None`, so the call
    raises and the original string is kept. Capitalised forms do convert."""
    result = _run("Literal Eval", {"low": "true", "cap": "True", "n": "None"})
    assert result["low"] == "true"
    assert result["cap"] is True
    assert result["n"] is None


def test_literal_eval_keeps_a_value_that_fails_to_parse():
    result = _run("Literal Eval", {"a": "[1, "})
    assert result == {"a": "[1, "}


# ---------------------------------------------------------------------------
# Combine
# ---------------------------------------------------------------------------


def test_combine_merges_objects_and_collects_repeated_keys_into_a_list():
    result = _run("Combine", [{"a": 1, "b": "x"}, {"a": 2}])
    assert result == {"a": [1, 2], "b": "x"}


def test_combine_extends_an_existing_list_rather_than_nesting_it():
    result = _run("Combine", [{"a": [1, 2]}, {"a": [3]}])
    assert result == {"a": [1, 2, 3]}


def test_combine_of_a_single_object_returns_it_unchanged():
    assert _run("Combine", [{"a": 1}]) == {"a": 1}


# ---------------------------------------------------------------------------
# Append or Update / Remove Keys / Rename Keys
# ---------------------------------------------------------------------------


def test_append_or_update_writes_top_level_pairs():
    result = _run("Append or Update", {"a": 1}, append_update_data={"b": 2, "a": 9})
    assert result == {"a": 9, "b": 2}


def test_remove_keys_removes_them_at_every_depth():
    result = _run(
        "Remove Keys",
        {"a": 1, "gizli": 2, "n": {"gizli": 3, "b": 4}, "lst": [{"gizli": 5}]},
        remove_keys_input=["gizli"],
    )
    assert result == {"a": 1, "n": {"b": 4}, "lst": [{}]}


def test_rename_keys_renames_at_every_depth():
    result = _run(
        "Rename Keys",
        {"eski": 1, "n": {"eski": 2}, "lst": [{"eski": 3}]},
        rename_keys_input={"eski": "yeni"},
    )
    assert result == {"yeni": 1, "n": {"yeni": 2}, "lst": [{"yeni": 3}]}


# ---------------------------------------------------------------------------
# Path Selection / JQ Expression — jq's own query language
# ---------------------------------------------------------------------------


def test_path_selection_extracts_the_value_at_a_jq_path():
    result = _run("Path Selection", {"user": {"name": "Ada"}}, selected_key=".user.name")
    assert result == {"result": "Ada"}


def test_path_selection_returns_an_object_result_as_is():
    result = _run("Path Selection", {"user": {"name": "Ada"}}, selected_key=".user")
    assert result == {"name": "Ada"}


def test_path_selection_reports_its_error_instead_of_raising():
    """Langflow swallows this one and returns {"error": ...}; JQ Expression
    raises. The asymmetry is theirs and is preserved."""
    result = _run("Path Selection", {"a": 1}, selected_key="")
    assert "error" in result


def test_jq_expression_runs_a_jq_program():
    result = _run("JQ Expression", {"items": [1, 2, 3]}, query=".items | length")
    assert result == {"result": 3}


def test_jq_expression_flattens_a_single_result_but_keeps_several():
    several = _run("JQ Expression", {"items": [1, 2]}, query=".items[]")
    assert several == {"result": [1, 2]}


def test_jq_expression_requires_a_query():
    with pytest.raises(ValueError, match="cannot be blank"):
        _run("JQ Expression", {"a": 1}, query="  ")


def test_jq_expression_raises_when_the_path_is_missing():
    with pytest.raises(ValueError):
        _run("JQ Expression", {"a": 1}, query=".yok")


def test_jq_expression_unwraps_a_data_envelope_before_querying():
    """Langflow feeds `data_json["data"]` to jq when the payload carries one."""
    result = _run("JQ Expression", {"data": {"n": 5}}, query=".n")
    assert result == {"result": 5}
