from core.mcp_auth import _is_internal_mcp_url


def test_internal_mcp_url_detection_accepts_canonical_tools_service_path() -> None:
    assert _is_internal_mcp_url("http://kong:8000/internal/tools-service/mcp")


def test_internal_mcp_url_detection_rejects_legacy_internal_mcp_path() -> None:
    assert not _is_internal_mcp_url("http://kong:8000/internal/mcp")
