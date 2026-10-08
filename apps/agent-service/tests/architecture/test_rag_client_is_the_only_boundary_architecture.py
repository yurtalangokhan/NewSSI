"""Architectural test: one way out to rag-service.

``integrations.rag_client`` exists because call sites used to hand-roll dict
payloads against a schema that lives in another service, and two of them had
drifted: graph search sent ``collection_ids`` where rag-service wants
``collection_id`` (a 422 the user saw as "LLM provider error"), and document
search read ``content`` from chunks rag-service keys as ``page_content``
(retrieved text silently dropped, so the model answered "not in the documents").

The client ended that for the search endpoints. The collection endpoints kept a
second boundary in ``service.flows.resolvers`` — its own request helper, its own
hardcoded timeout that ignored ``configs/resilience.yaml``, and the ``uuid``/
``id`` fallback written out three more times. These tests keep the one boundary
one boundary.

``api.routes.proxy_route`` is exempt: it forwards raw client requests rather
than calling a typed endpoint, so it needs the base URL, not the contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
RAG_CLIENT = SRC_DIR / "integrations" / "rag_client.py"

#: Modules allowed to know how a rag-service request is built.
TRANSPORT_OWNERS = {
    Path("integrations/rag_client.py"),
    Path("core/http/rag_http.py"),
    # The proxy forwards whole requests; it needs the address, not the schema.
    Path("api/routes/proxy_route.py"),
}

#: Building a URL for rag-service is the tell that a caller is about to
#: construct its own request.
TRANSPORT_SYMBOLS = {"rag_url", "rag_base_url", "rag_auth_headers", "rag_timeout_seconds"}


def _python_files() -> list[Path]:
    return [p for p in sorted(SRC_DIR.rglob("*.py")) if "__pycache__" not in p.parts]


def test_the_rag_client_exists_and_is_populated():
    """Guard the guard: the checks below mean nothing without the client."""
    assert RAG_CLIENT.is_file(), "integrations/rag_client.py must exist"
    tree = ast.parse(RAG_CLIENT.read_text(encoding="utf-8"))
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"search_documents", "list_collections", "list_knowledge_sources"} <= functions


def test_only_the_transport_owners_build_rag_service_requests():
    violations: list[str] = []

    for py_file in _python_files():
        rel_path = py_file.relative_to(SRC_DIR)
        if rel_path in TRANSPORT_OWNERS:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != "core.http.rag_http":
                continue
            for alias in node.names:
                if alias.name in TRANSPORT_SYMBOLS:
                    violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")

    assert not violations, (
        "rag-service requests must go through integrations.rag_client, which owns "
        "the contract and reads the configured timeout:\n" + "\n".join(violations)
    )


#: Call sites that still reach rag-service without the client, and what each
#: one would need. This list is a ratchet: it may shrink, never grow.
KNOWN_DIRECT_CALLERS = {
    # Health probe against /docs — no schema, but no configured timeout either.
    "service/ingest/ingestion_service.py",
    # Calls /datasources/knowledge-selector, which rag_client now owns, but with
    # an internal service token instead of the caller's bearer token.
    "service/personas/persona_service.py",
}


def test_no_new_direct_rag_service_caller_appears():
    """Only the client should issue rag-service requests; the rest are tracked debt.

    Consolidating the remaining callers needs decisions this test cannot make —
    the persona path authenticates as the service rather than the user, and the
    ingest probe wants a shorter timeout than a query does. Until then, at least
    the set cannot grow silently.
    """
    callers: set[str] = set()

    for py_file in _python_files():
        rel_path = py_file.relative_to(SRC_DIR)
        if rel_path in TRANSPORT_OWNERS:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if any(isinstance(a, ast.Attribute) and a.attr == "RAG_SERVICE" for a in node.args):
                callers.add(rel_path.as_posix())

    new_callers = sorted(callers - KNOWN_DIRECT_CALLERS)
    assert not new_callers, (
        "New direct rag-service callers — route them through integrations.rag_client:\n"
        + "\n".join(new_callers)
    )

    resolved = sorted(KNOWN_DIRECT_CALLERS - callers)
    assert not resolved, (
        "These no longer call rag-service directly; drop them from "
        "KNOWN_DIRECT_CALLERS so the ratchet keeps holding:\n" + "\n".join(resolved)
    )


@pytest.mark.parametrize("wire_key", ["page_content", "collection_ids"])
def test_rag_service_wire_keys_are_known_in_one_place(wire_key: str):
    """rag-service's field names belong to the client, not to its callers.

    Each of these is a name this service does not choose. Spelling one out
    anywhere else means a rag-service schema change breaks in two places.
    """
    violations: list[str] = []

    for py_file in _python_files():
        rel_path = py_file.relative_to(SRC_DIR)
        if rel_path in TRANSPORT_OWNERS:
            continue
        source = py_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or f'"{wire_key}"' not in line:
                continue
            violations.append(f"{rel_path}:{lineno} {stripped[:80]}")

    assert not violations, (
        f"'{wire_key}' is rag-service's field name; keep it inside rag_client:\n"
        + "\n".join(violations)
    )
