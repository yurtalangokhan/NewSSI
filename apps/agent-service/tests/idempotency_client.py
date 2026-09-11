"""Test client that satisfies the idempotency-key requirement.

Mutating endpoints are key-enforced (see ``core/idempotency.py``). The browser
client attaches a key to every mutating request automatically
(``apps/web/src/lib/fetcher.ts``), so tests exercising those routes would
otherwise repeat the header at every call site — and one fixed key is
rejected as reuse as soon as two requests differ.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


class IdempotentTestClient(TestClient):
    """A ``TestClient`` that supplies a fresh ``Idempotency-Key`` per request.

    Mutating endpoints are key-enforced (see ``core/idempotency.py``); the
    browser client attaches a key to every mutating request automatically
    (``apps/web/src/lib/fetcher.ts``), so tests that exercise those routes
    would otherwise have to repeat the header at every call site — and a
    single fixed key is rejected as reuse once two requests differ.
    """

    def request(self, method: str, url, **kwargs):  # type: ignore[override]
        headers = dict(kwargs.pop("headers", None) or {})
        if not any(k.lower() == "idempotency-key" for k in headers):
            headers["Idempotency-Key"] = f"test-{uuid.uuid4()}"
        return super().request(method, url, headers=headers, **kwargs)
