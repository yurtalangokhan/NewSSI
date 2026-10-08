"""Trusted identity set by the middleware must reach the tool that runs.

The middleware sets `TrustedToolContext` into a ContextVar during
`BaseHTTPMiddleware.dispatch`; the tool body reads it back with
`get_current_trusted_context()`. Whether those two run in the same
`contextvars` context is a property of FastMCP's streamable-HTTP session
model, not of this codebase -- a stateful MCP session dispatches
`tools/call` through its own session manager, and if that ever moves the
handler onto a task spawned before dispatch ran, every tool would silently
see `user_id=None` and call rag-service as nobody.

That is not a failure any unit test of either half would catch, and
"probably still works" is not a property to carry on trust across a FastMCP
upgrade, so this drives the real transport end to end: a full MCP session
(initialize -> initialized -> tools/call) against the real app, asserting
the identity from the request headers arrives in the outbound call the tool
makes.
"""

from __future__ import annotations

import pytest

INTERNAL_TOKEN = "trusted-context-probe-token"

HEADERS = {
    "Authorization": "Bearer test-key",
    "x-internal-token": INTERNAL_TOKEN,
    "x-user-id": "user-42",
    "x-tenant-id": "tenant-7",
    "Accept": "application/json, text/event-stream",
}


def _retrieval_answer() -> dict:
    return {
        "kind": "vector",
        "collection_id": "col-1",
        "collection_name": "Probe",
        "context": "",
        "hits": [
            {
                "id": "chunk-1",
                "content": "some knowledge",
                "score": 0.9,
                "source": "vector",
                "metadata": {"source": "probe.pdf"},
            }
        ],
        "graph": None,
    }


@pytest.fixture
def capture_retrieval(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    import httpx

    from src.knowledge.retrieval_client import RagRetrievalClient
    from src.knowledge.search_service import KnowledgeSearchService
    from src.tools import knowledge_tools

    captured: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(request.headers))
        return httpx.Response(
            200,
            json={"statusCode": 200, "message": None, "data": _retrieval_answer(), "error": None},
        )

    def build_service() -> KnowledgeSearchService:
        return KnowledgeSearchService(
            RagRetrievalClient(
                retrieval_url="http://rag-service/api/v1/retrieval",
                internal_token=INTERNAL_TOKEN,
                transport=httpx.MockTransport(handler),
            )
        )

    monkeypatch.setattr(knowledge_tools, "build_knowledge_search_service", build_service)
    # The middleware validates the header against the token it loads itself.
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", INTERNAL_TOKEN)
    # The MCP verifier (src/core/auth.py) reads that token from settings rather
    # than from the environment, so it needs the same value.
    monkeypatch.setattr("src.core.auth._get_internal_service_token", lambda: INTERNAL_TOKEN)
    return captured


def _result_of(response) -> dict:
    """The JSON-RPC ``result`` of a reply sent as plain JSON or as one SSE event."""
    import json

    body = response.text
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        body = next(
            line.removeprefix("data:").strip()
            for line in body.splitlines()
            if line.startswith("data:")
        )
    return json.loads(body)["result"]


def _rpc(client, payload: dict, session_id: str | None = None):
    headers = dict(HEADERS)
    if session_id:
        headers["mcp-session-id"] = session_id
    return client.post("/mcp", json=payload, headers=headers)


def _open_session(client) -> str:
    initialized = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "trusted-context-test", "version": "1.0"},
            },
        },
    )
    assert initialized.status_code == 200, initialized.text
    session_id = initialized.headers.get("mcp-session-id")
    assert session_id, "server issued no MCP session id"

    ack = _rpc(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    assert ack.status_code == 202, ack.text
    return session_id


def test_the_callers_identity_reaches_the_tool_body(http_client, capture_retrieval) -> None:
    session_id = _open_session(http_client)

    called = _rpc(
        http_client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "database_search",
                "arguments": {"query": "anything", "collection_ids": ["col-1"]},
            },
        },
        session_id,
    )

    assert called.status_code == 200, called.text
    assert capture_retrieval, "the tool never reached its outbound call"
    outbound = capture_retrieval[0]
    assert outbound.get("x-user-id") == "user-42", (
        "the tool ran without the caller's identity: the trusted context set by "
        "the middleware did not reach the tool body"
    )
    assert outbound.get("x-tenant-id") == "tenant-7"


def test_knowledge_evidence_travels_as_structured_content(http_client, capture_retrieval) -> None:
    """The model reads ``content``; the evidence rides ``structuredContent``."""
    session_id = _open_session(http_client)

    called = _rpc(
        http_client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "database_search",
                "arguments": {"query": "anything", "collection_ids": ["col-1"]},
            },
        },
        session_id,
    )

    assert called.status_code == 200, called.text
    result = _result_of(called)
    assert result["content"][0]["text"] == "[1] (probe.pdf)\nsome knowledge"
    evidence = result["structuredContent"]
    assert evidence["tool"] == "database_search"
    assert evidence["chunks"][0]["content"] == "some knowledge"


def test_a_caller_without_the_internal_token_gets_no_trusted_identity(
    http_client, capture_retrieval, monkeypatch
) -> None:
    """The context is granted by the internal token, not by asking for it.

    The caller here is Gateway-authenticated as a *user* — that is what reaches
    this service in production — and its ``x-user-id`` must still not appear on
    the outbound request: only the internal service token grants a trusted
    context.
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "src.core.auth.get_user_service_permissions",
        AsyncMock(return_value=["tool:execute"]),
    )
    headers = {key: value for key, value in HEADERS.items() if key != "x-internal-token"}
    headers.update({"x-gateway-token": INTERNAL_TOKEN, "x-gateway-user-id": "user-42"})

    initialized = http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "no-token-test", "version": "1.0"},
            },
        },
        headers=headers,
    )
    assert initialized.status_code == 200, initialized.text
    session_id = initialized.headers["mcp-session-id"]

    http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={**headers, "mcp-session-id": session_id},
    )
    called = http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "database_search",
                "arguments": {"query": "anything", "collection_ids": ["col-1"]},
            },
        },
        headers={**headers, "mcp-session-id": session_id},
    )

    assert called.status_code == 200, called.text
    assert capture_retrieval, "the tool never reached its outbound call"
    assert "x-user-id" not in capture_retrieval[0], (
        "a spoofed x-user-id was honoured without the internal service token"
    )
