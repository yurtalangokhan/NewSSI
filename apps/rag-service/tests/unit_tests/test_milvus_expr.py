"""Milvus has no parameter binding for boolean expressions, so file_id and
document_id were being interpolated into an f-string filter (spec T1).
metadata_equals allow-lists both the key and the value before building
the expression string.
"""

import pytest

from src.shared.milvus_expr import (
    InvalidExpressionValueError,
    metadata_equals,
    metadata_in,
    metadata_path,
)


def test_builds_an_equality_expression():
    expr = metadata_equals(
        "metadata", "file_id", "0f0c3d3e-6f5f-4b1b-9a4a-2f0b6b2a1c11"
    )
    assert expr == 'metadata["file_id"] == "0f0c3d3e-6f5f-4b1b-9a4a-2f0b6b2a1c11"'


@pytest.mark.parametrize(
    "value",
    [
        'x" or metadata["file_id"] != "',
        "x' or 1==1",
        'x\\" or true',
        "x or true",
        "../etc",
        "",
        "a" * 200,
    ],
)
def test_rejects_values_that_are_not_identifiers(value):
    with pytest.raises(InvalidExpressionValueError):
        metadata_equals("metadata", "file_id", value)


def test_rejects_an_unknown_key():
    with pytest.raises(InvalidExpressionValueError):
        metadata_equals("metadata", 'file_id"] or true or metadata["x', "abc")


def test_rejects_an_unknown_field():
    with pytest.raises(InvalidExpressionValueError):
        metadata_equals('metadata"] or true or x["y', "file_id", "abc")


def test_builds_a_membership_expression():
    expr = metadata_in("metadata", "_record_key", ["a" * 40, "b" * 40])
    assert expr == f'metadata["_record_key"] in ["{"a" * 40}", "{"b" * 40}"]'


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["abc", 'x"] or true or ["'],
        ["abc", ""],
        ["a" * 200],
    ],
)
def test_membership_rejects_values_that_are_not_identifiers(values):
    with pytest.raises(InvalidExpressionValueError):
        metadata_in("metadata", "_record_key", values)


def test_membership_rejects_an_unknown_key_and_field():
    with pytest.raises(InvalidExpressionValueError):
        metadata_in("metadata", '_record_key"] or true or metadata["x', ["abc"])
    with pytest.raises(InvalidExpressionValueError):
        metadata_in('metadata"] or true or x["y', "_record_key", ["abc"])


def test_builds_a_metadata_path():
    # One spelling for the filters above and for a JSON path index on the key.
    assert metadata_path("metadata", "_record_key") == 'metadata["_record_key"]'


def test_metadata_path_rejects_an_unknown_key_and_field():
    with pytest.raises(InvalidExpressionValueError):
        metadata_path("metadata", '_record_key"] or true or metadata["x')
    with pytest.raises(InvalidExpressionValueError):
        metadata_path('metadata"] or true or x["y', "_record_key")
