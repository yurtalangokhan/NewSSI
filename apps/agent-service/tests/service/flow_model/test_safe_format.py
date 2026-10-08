"""str.format lets a template walk attributes from any value it is given:
{x.__init__.__globals__[os].environ} reads the process environment through
PromptTemplate's scratch-variable substitution. safe_format resolves only
top-level names and stringifies every value. Spec T1."""

import pytest

from service.flow_model.safe_format import UnsafeTemplateError, safe_format, validate_template


def test_plain_substitution_works():
    assert safe_format("Hello {name}", {"name": "Ada"}) == "Hello Ada"


def test_missing_key_raises_key_error():
    """Matches str.format(**values)'s own behaviour for a missing name --
    and test_prompt_template_node_raises_on_missing_variable in
    tests/agents/graphs/test_execution_nodes.py, which already relies on
    this to surface a clear error instead of silently rendering empty."""
    with pytest.raises(KeyError):
        safe_format("Hello {name}", {})


@pytest.mark.parametrize(
    "template",
    [
        "{x.__init__.__globals__[os].environ}",
        "{x.__class__}",
        "{x.__class__.__mro__}",
        "{x[0].__dict__}",
    ],
)
def test_attribute_and_index_access_are_rejected(template):
    with pytest.raises(UnsafeTemplateError):
        safe_format(template, {"x": object()})


def test_values_are_stringified():
    assert safe_format("{n}", {"n": {"a": 1}}) == "{'a': 1}"


def test_format_spec_cannot_be_used_to_explode_output():
    with pytest.raises(UnsafeTemplateError):
        safe_format("{n:>1000000}", {"n": "x"})


def test_validate_template_accepts_plain_placeholders():
    validate_template("Hello {name}, you are {age:>3} years old")


@pytest.mark.parametrize(
    "template",
    [
        "{x.__init__.__globals__[os].environ}",
        "{x.__class__}",
        "{x[0]}",
        "{0}",
        "{}",
        "{n:>1000000}",
        "unterminated {",
    ],
)
def test_validate_template_rejects_the_same_shapes_safe_format_does(template):
    with pytest.raises(UnsafeTemplateError):
        validate_template(template)
