from core.security.mcp.mcp_auth import _is_internal_mcp_url


def test_internal_mcp_url_detection_accepts_canonical_tools_service_path(monkeypatch) -> None:
    # The check compares against the configured internal URL, so pin it here.
    monkeypatch.setenv("INTERNAL_TOOLS_SERVICE_URL", "http://apisix:8000/internal/tools-service/mcp")
    assert _is_internal_mcp_url("http://apisix:8000/internal/tools-service/mcp")


def test_internal_mcp_url_detection_rejects_legacy_internal_mcp_path() -> None:
    assert not _is_internal_mcp_url("http://apisix:8000/internal/mcp")
