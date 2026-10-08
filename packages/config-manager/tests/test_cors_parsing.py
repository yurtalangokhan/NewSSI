"""Reading CORS_ALLOWED_ORIGINS out of configuration.

This is configuration parsing, so it is tested here rather than in the security
package. The safety rule that consumes its output is tested in
``packages/security/tests/test_cors.py``.
"""

import pytest

from config_manager import DEFAULT_ALLOWED_ORIGIN, parse_allowed_origins


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unset_falls_back_to_the_development_origin(raw):
    """Falling back to '*' would open CORS on a misconfigured deployment."""
    assert parse_allowed_origins(raw) == [DEFAULT_ALLOWED_ORIGIN]


def test_parses_a_json_array():
    assert parse_allowed_origins('["https://a.test", "https://b.test"]') == [
        "https://a.test",
        "https://b.test",
    ]


def test_parses_a_json_string():
    assert parse_allowed_origins('"https://a.test"') == ["https://a.test"]


def test_parses_a_comma_separated_list():
    assert parse_allowed_origins("https://a.test, https://b.test") == [
        "https://a.test",
        "https://b.test",
    ]


def test_strips_quotes_and_brackets_from_a_bare_list():
    assert parse_allowed_origins("['https://a.test','https://b.test']") == [
        "https://a.test",
        "https://b.test",
    ]


def test_drops_blank_entries():
    assert parse_allowed_origins("https://a.test,,  ,https://b.test") == [
        "https://a.test",
        "https://b.test",
    ]


def test_an_unparseable_value_falls_back_rather_than_opening_up():
    """A typo in the env file must fail closed, not yield '*'."""
    assert parse_allowed_origins("not a list at all") == ["not a list at all"]
