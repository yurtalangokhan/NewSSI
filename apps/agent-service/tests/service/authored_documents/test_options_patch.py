from core.types.authored_documents import DocumentKind
from service.authored_documents.options_patch import merge_options, normalize_options


def test_normalize_drops_defaults_and_invalid_values() -> None:
    assert normalize_options(DocumentKind.DOCUMENT, None) == {}
    normalized = normalize_options(DocumentKind.DOCUMENT, {"theme": "corporate_blue", "toc": {"enabled": True}})
    assert normalized["theme"] == "corporate_blue"
    assert normalized["toc"]["enabled"] is True


def test_merge_is_deep_and_null_removes_a_key() -> None:
    current = normalize_options(DocumentKind.DOCUMENT, {"theme": "corporate_blue", "toc": {"enabled": True}})
    merged = merge_options(DocumentKind.DOCUMENT, current, {"toc": None, "watermark": {"text": "TASLAK"}})
    assert merged["theme"] == "corporate_blue"
    assert "toc" not in merged
    assert merged["watermark"]["text"] == "TASLAK"
