"""Idempotency scopes use the same trusted identity as MCP authentication."""
from types import SimpleNamespace

import pytest
from fastapi import Request

from src.core import idempotency_principal

SECRET = "test-gateway-secret"

@pytest.mark.parametrize("headers, expected", [
    ({"x-gateway-token": SECRET, "x-gateway-user-id": "user-1"}, "user-1"),
    ({"x-internal-service-token": SECRET}, "internal-service"),
    ({"x-internal-service-token": SECRET, "x-user-id": "user-2"}, "user-2"),
    ({"x-gateway-user-id": "forged", "authorization": "Bearer anything"}, None),
    ({"cookie": "access_token=anything"}, None),
    ({}, None),
])
async def test_scopes_only_trusted_identity(monkeypatch, headers, expected):
    monkeypatch.setattr(
        idempotency_principal,
        "env",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN=SECRET),
    )
    request = Request({"type": "http", "method": "POST", "path": "/mcp",
                       "headers": [(k.encode(), v.encode()) for k, v in headers.items()]})
    assert await idempotency_principal.extract_principal_from_jwt(request) == expected
