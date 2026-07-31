from __future__ import annotations

from types import SimpleNamespace

from agents import tools


class _FakeResponse:
    status_code = 200
    text = "{}"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "context": "== Knowledge Graph Context ==\nTelekomünikasyon --[HAS]--> Türksat",
            "nodes": [{"name": "Telekomünikasyon"}],
            "edges": [{"type": "HAS"}],
            "score": 1.0,
        }


def test_graph_search_calls_versioned_rag_endpoint(monkeypatch):
    captured: dict[str, str] = {}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, *, json: dict, headers: dict):
            captured["url"] = url
            captured["collection_id"] = json["collection_id"]
            captured["include_vector_context"] = json["include_vector_context"]
            captured["token_header"] = headers["X-Internal-Service-Token"]
            return _FakeResponse()

    monkeypatch.setattr(tools, "_LANGCONNECT_BASE_URL", "http://kong/internal/rag-service")
    monkeypatch.setattr(tools, "_LANGCONNECT_SERVICE_TOKEN", "internal-token")
    monkeypatch.setattr("httpx.Client", FakeClient)

    result = tools.graph_search_func(
        "Telekomünikasyon",
        SimpleNamespace(
            get=lambda key, default=None: {
                "configurable": {
                    "rag_config": {
                        "knowledge_graph": [
                            "a493830e-b8aa-4bd7-95b5-010ead920298",
                        ],
                    },
                },
            }.get(key, default),
        ),
    )

    assert captured["url"] == "http://kong/internal/rag-service/api/v1/graph/search"
    assert captured["collection_id"] == "a493830e-b8aa-4bd7-95b5-010ead920298"
    assert captured["include_vector_context"] is False
    assert captured["token_header"] == "internal-token"
    assert "Telekomünikasyon" in result


def test_langconnect_url_does_not_duplicate_api_prefix(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_LANGCONNECT_BASE_URL",
        "http://kong/internal/rag-service/api/v1",
    )

    assert (
        tools._langconnect_url("/graph/search")
        == "http://kong/internal/rag-service/api/v1/graph/search"
    )


def test_graph_search_prefers_internal_token_over_user_bearer(monkeypatch):
    captured: dict[str, dict[str, str]] = {}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, *, json: dict, headers: dict):
            captured["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(tools, "_LANGCONNECT_BASE_URL", "http://kong/internal/rag-service")
    monkeypatch.setattr(tools, "_LANGCONNECT_SERVICE_TOKEN", "internal-token")
    monkeypatch.setattr("httpx.Client", FakeClient)

    result = tools.graph_search_func(
        "Telekomünikasyon",
        SimpleNamespace(
            get=lambda key, default=None: {
                "configurable": {
                    "access_token": "not-yet-valid-user-token",
                    "rag_config": {
                        "knowledge_graph": [
                            "a493830e-b8aa-4bd7-95b5-010ead920298",
                        ],
                    },
                },
            }.get(key, default),
        ),
    )

    assert captured["headers"]["X-Internal-Service-Token"] == "internal-token"
    assert "Authorization" not in captured["headers"]
    assert "Telekomünikasyon" in result
