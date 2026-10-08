"""Helpers for tests that exercise routes behind Gateway authentication.

Services no longer authenticate anyone themselves, so a test that drives a real
route must present the same trusted headers Gateway sets.
"""

from __future__ import annotations

GATEWAY_SECRET = "test-gateway-secret"
GATEWAY_USER_ID = "dev-user"

GATEWAY_HEADERS = {
    "x-gateway-token": GATEWAY_SECRET,
    "x-gateway-user-id": GATEWAY_USER_ID,
    "x-gateway-email": "dev-user@local.dev",
    "x-gateway-username": "dev-user",
}


def use_gateway_auth(monkeypatch) -> None:
    """Configure the service to trust the test Gateway secret."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", GATEWAY_SECRET)


def allow_all_permissions(monkeypatch) -> None:
    """Grant every fine-grained permission for a test's overridden user.

    ``require_permission`` resolves permissions through user-service. Tests that
    override ``require_user`` with a fake identity used to ride on a hardcoded
    ``dev-user`` grant; that grant is gone, so the seam is now explicit.
    """

    class _AllowAll:
        async def has_permission(self, *_args, **_kwargs) -> bool:
            return True

    monkeypatch.setattr(
        "integrations.authorization_client.get_authorization_client",
        lambda: _AllowAll(),
    )
