from src.core.auth import _get_valid_api_keys
from src.core.base import BaseToolCategory


def test_get_valid_api_keys_trims_and_drops_empty_values(monkeypatch):
    monkeypatch.setenv("VALID_API_KEYS", " alpha, , beta ,")

    assert _get_valid_api_keys() == {"alpha", "beta"}


def test_parse_json_param_returns_empty_dict_for_missing_or_invalid_input():
    assert BaseToolCategory.parse_json_param(None) == {}
    assert BaseToolCategory.parse_json_param("not-json") == {}


def test_parse_json_param_returns_decoded_dict():
    assert BaseToolCategory.parse_json_param('{"name": "tools"}') == {"name": "tools"}
