"""Regression test: require_permission must check the real user-service id,
not the raw Keycloak `sub`.

AuthService.build_authenticated_user() (the normal, successful Keycloak JWT
decode path -- see require_user in api/dependencies.py) never populates
claims["user_service_user"]; that claim is only ever attached by the rarer
authenticate_with_user_service() fallback. user.user_id is therefore the
Keycloak `sub` for the overwhelming majority of authenticated requests.

user-service's `users.id` (the primary key that composite_roles/user_roles/
PermissionResolverService key off of) is a separately generated UUID, never
equal to the Keycloak subject -- see user_repository.upsert_by_keycloak_id,
which never sets `id` from `keycloak_id`. So checking a permission against
`user.user_id` on the normal path asks user-service about a user id that
doesn't exist, and every fine-grained permission check denies regardless of
what's actually granted in the database.

AuthService.resolve_user_identity() resolves this correctly: it falls back to
a live get_user_by_keycloak_id lookup when the claim is absent.
require_permission must use that resolution instead of its own inline
(Keycloak-sub-on-miss) fallback.
"""

from __future__ import annotations

import pytest

import service.auth.auth_service as auth_service_module
from api.dependencies import require_permission
from service.auth.auth_service import AuthenticatedUser

KEYCLOAK_SUB = "11111111-1111-1111-1111-111111111111"
REAL_USER_SERVICE_ID = "22222222-2222-2222-2222-222222222222"


def _user_without_user_service_claim() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=KEYCLOAK_SUB,
        email="user@example.com",
        claims={"sub": KEYCLOAK_SUB},
        access_token="token-abc",
    )


@pytest.mark.asyncio
async def test_check_permission_resolves_real_user_service_id_not_keycloak_sub(
    monkeypatch,
):
    async def fake_resolve_user_identity(self, *, token, user_id, user=None):
        assert user_id == KEYCLOAK_SUB
        return {"primary_user_id": REAL_USER_SERVICE_ID}

    monkeypatch.setattr(
        auth_service_module.AuthService,
        "resolve_user_identity",
        fake_resolve_user_identity,
    )

    captured: dict[str, str] = {}

    class FakeAuthorizationClient:
        async def has_permission(self, user_id, permission, access_token):
            captured["user_id"] = user_id
            return True

    monkeypatch.setattr(
        "integrations.authorization_client.get_authorization_client",
        lambda: FakeAuthorizationClient(),
    )

    check_permission = require_permission("flow:read")
    result = await check_permission(user=_user_without_user_service_claim())

    assert captured["user_id"] == REAL_USER_SERVICE_ID
    assert result.user_id == KEYCLOAK_SUB


@pytest.mark.asyncio
async def test_check_permission_still_uses_claim_id_when_already_present(monkeypatch):
    """When user_service_user IS already in claims (the
    authenticate_with_user_service fallback path), no extra resolution call
    should be needed -- resolve_user_identity is still the single source of
    truth, but it must return that same id without a live lookup."""

    async def fake_resolve_user_identity(self, *, token, user_id, user=None):
        claimed = user.claims.get("user_service_user") if user else None
        assert isinstance(claimed, dict)
        return {"primary_user_id": claimed["id"]}

    monkeypatch.setattr(
        auth_service_module.AuthService,
        "resolve_user_identity",
        fake_resolve_user_identity,
    )

    captured: dict[str, str] = {}

    class FakeAuthorizationClient:
        async def has_permission(self, user_id, permission, access_token):
            captured["user_id"] = user_id
            return True

    monkeypatch.setattr(
        "integrations.authorization_client.get_authorization_client",
        lambda: FakeAuthorizationClient(),
    )

    user = AuthenticatedUser(
        user_id=KEYCLOAK_SUB,
        email="user@example.com",
        claims={"user_service_user": {"id": REAL_USER_SERVICE_ID}},
        access_token="token-abc",
    )

    check_permission = require_permission("flow:read")
    await check_permission(user=user)

    assert captured["user_id"] == REAL_USER_SERVICE_ID


@pytest.mark.asyncio
async def test_internal_service_bypasses_resolution(monkeypatch):
    """The dev-mode / internal-service bypass must not start making a
    resolve_user_identity call -- it never needs one."""

    def fail_if_called(*args, **kwargs):
        raise AssertionError("resolve_user_identity should not be called for bypass users")

    monkeypatch.setattr(
        auth_service_module.AuthService,
        "resolve_user_identity",
        fail_if_called,
    )

    check_permission = require_permission("flow:read")

    internal_user = AuthenticatedUser(user_id="internal-service", email="internal@service.local")
    result = await check_permission(user=internal_user)
    assert result.user_id == "internal-service"


@pytest.mark.asyncio
async def test_dev_user_requires_explicit_permission(monkeypatch):
    from core.exceptions import ForbiddenError

    class Denied:
        async def has_permission(self, user_id, permission, access_token):
            assert user_id == "dev-user"
            return False

    monkeypatch.setattr("integrations.authorization_client.get_authorization_client", lambda: Denied())
    with pytest.raises(ForbiddenError):
        await require_permission("flow:read")(
            user=AuthenticatedUser(user_id="dev-user", email="dev@local.dev")
        )
