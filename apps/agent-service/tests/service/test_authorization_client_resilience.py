"""AuthorizationClient must fail closed, not leak an internal status code.

_fetch_permission_decision() tries authorize_user_permission() first and
falls back to get_user_permissions() if that raises ApplicationError. The
fallback call itself was never wrapped: if it also failed (a user-service
hiccup, a misconfigured internal token, anything), its ApplicationError
propagated all the way out of has_permission() with *its own* status code
attached (e.g. a raw 401), past require_permission's normal 403-on-denial
path, straight to the browser. authenticatedFetch treats any 401 as an
expired session and forces a logout -- so a transient permission-check
plumbing failure could log a user out of an otherwise perfectly valid
session, instead of just denying the one action being checked.
"""

import pytest
from error_contract import CircuitBreakerOpenError, DependencyUnavailableError

from integrations.authorization_client import AuthorizationClient


def _dependency_unavailable() -> DependencyUnavailableError:
    return DependencyUnavailableError(
        code="user_service.request_failed",
        message="User service request failed.",
        details={},
    )


@pytest.mark.asyncio
async def test_has_permission_denies_when_both_lookups_fail(monkeypatch) -> None:
    async def fail_authorize(*args, **kwargs):
        raise _dependency_unavailable()

    async def fail_permissions(*args, **kwargs):
        raise _dependency_unavailable()

    monkeypatch.setattr(
        "integrations.user_service_client.authorize_user_permission", fail_authorize
    )
    monkeypatch.setattr("integrations.user_service_client.get_user_permissions", fail_permissions)

    client = AuthorizationClient()

    assert await client.has_permission("user-1", "mcp_provider:sync") is False


@pytest.mark.asyncio
async def test_has_permission_still_uses_fallback_permissions_list(monkeypatch) -> None:
    """The fallback path itself must still work when only the primary call fails."""
    from error_contract import ApplicationError

    async def fail_authorize(*args, **kwargs):
        raise ApplicationError(status_code=401, code="user_service.error", message="x")

    async def fake_permissions(*args, **kwargs):
        return {"permissions": ["mcp_provider:sync"]}

    monkeypatch.setattr(
        "integrations.user_service_client.authorize_user_permission", fail_authorize
    )
    monkeypatch.setattr("integrations.user_service_client.get_user_permissions", fake_permissions)

    client = AuthorizationClient()

    assert await client.has_permission("user-1", "mcp_provider:sync") is True


@pytest.mark.asyncio
async def test_has_permission_denies_when_user_service_circuit_is_open(monkeypatch) -> None:
    class OpenCircuit:
        async def __aenter__(self):
            raise CircuitBreakerOpenError("user-service", 30.0)

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "core.http.outbound.get_circuit_breaker",
        lambda _dependency: OpenCircuit(),
    )

    client = AuthorizationClient()

    assert await client.has_permission("user-1", "datasource:read") is False
