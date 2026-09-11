"""Tests for the Structured Output schema builder.

Two functions with deliberately different contracts:

- ``schema_errors`` is pure and **total** — the validator calls it on stored,
  possibly hand-edited rows, and a validator must never raise.
- ``build_output_model`` raises, because by the time the compiler calls it the
  schema has already been validated; a bad one there is a programming error,
  not user input.
"""

from __future__ import annotations

import pytest

from domain.flows.output_schema import build_output_model, schema_errors


def _row(name="baslik", type_="str", multiple=False, description="x"):
    return {"name": name, "description": description, "type": type_, "multiple": multiple}


# ---------------------------------------------------------------------------
# schema_errors — pure, total
# ---------------------------------------------------------------------------


def test_a_well_formed_schema_has_no_errors():
    assert schema_errors([_row(), _row(name="tutar", type_="float")]) == []


def test_an_empty_schema_is_an_error():
    assert schema_errors([]) != []
    assert schema_errors(None) != []


def test_a_row_without_a_name_is_an_error():
    assert schema_errors([_row(name="")]) != []
    assert schema_errors([{"type": "str"}]) != []


def test_a_name_that_is_not_a_field_identifier_is_an_error():
    """Pydantic builds real attributes from these, so a name with a space, a
    dash, or a leading underscore cannot become a field."""
    for bad in ("iki kelime", "tire-li", "_gizli", "1sayi"):
        assert schema_errors([_row(name=bad)]) != [], bad


def test_an_unknown_type_is_an_error():
    assert schema_errors([_row(type_="datetime")]) != []


def test_duplicate_names_are_an_error():
    """Two rows writing the same field silently lose one of them."""
    assert schema_errors([_row(name="a"), _row(name="a")]) != []


def test_every_supported_type_is_accepted():
    for supported in ("str", "int", "float", "bool", "dict"):
        assert schema_errors([_row(type_=supported)]) == [], supported


def test_a_missing_type_defaults_to_str():
    assert schema_errors([{"name": "baslik"}]) == []


def test_junk_rows_do_not_raise():
    """A hand-edited spec is untrusted input, not a crash."""
    assert schema_errors(["not a dict", 7, None]) != []
    assert schema_errors({"not": "a list"}) != []


# ---------------------------------------------------------------------------
# build_output_model
# ---------------------------------------------------------------------------


def test_builds_a_model_with_the_declared_fields_and_types():
    model = build_output_model(
        "Fatura",
        [
            _row(name="baslik", type_="str"),
            _row(name="tutar", type_="float"),
            _row(name="odendi", type_="bool"),
        ],
    )
    instance = model(baslik="Nisan", tutar=12.5, odendi=True)
    assert instance.baslik == "Nisan"
    assert instance.tutar == 12.5
    assert instance.odendi is True


def test_multiple_makes_the_field_a_list():
    model = build_output_model("M", [_row(name="etiketler", type_="str", multiple=True)])
    assert model(etiketler=["a", "b"]).etiketler == ["a", "b"]


def test_multiple_accepts_the_string_form_the_canvas_table_stores():
    """A TABLE cell round-trips through JSON as a string, so "True" must mean
    the same thing as True."""
    model = build_output_model("M", [_row(name="etiketler", type_="str", multiple="True")])
    assert model(etiketler=["a"]).etiketler == ["a"]


def test_the_description_reaches_the_field_so_the_llm_can_read_it():
    model = build_output_model("M", [_row(name="baslik", description="Faturanin basligi")])
    assert model.model_fields["baslik"].description == "Faturanin basligi"


def test_fields_are_optional_so_a_missing_value_is_null_not_a_failure():
    """Langflow's format instructions say to fill missing values with null
    rather than error; a required field would make the model refuse instead."""
    model = build_output_model("M", [_row(name="baslik"), _row(name="tutar", type_="int")])
    assert model().baslik is None


def test_an_invalid_schema_raises():
    with pytest.raises(ValueError):
        build_output_model("M", [])
    with pytest.raises(ValueError):
        build_output_model("M", [_row(name="tire-li")])


def test_the_schema_name_names_the_model():
    assert build_output_model("Fatura", [_row()]).__name__ == "Fatura"
