"""RAG-service accepts only callers Gateway has already authenticated."""

from types import SimpleNamespace

import pytest
from error_contract import UnauthorizedError

from src.shared import auth

SECRET = "shared-gateway-secret"


def _request(
    headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None
):
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _credentials(token: str):
    return SimpleNamespace(scheme="Bearer", credentials=token)


def _gateway_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "x-gateway-token": SECRET,
        "x-gateway-user-id": "keycloak-sub-1",
        "x-gateway-email": "ada@example.com",
        "x-gateway-username": "ada",
        "x-gateway-roles": "enduser",
    }
    headers.update(overrides)
    return headers


@pytest.fixture(autouse=True)
def gateway_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", SECRET)


# --------------------------------------------------------------------------
# Claim helpers (unchanged behaviour, still used for coarse role checks)
# --------------------------------------------------------------------------


def test_claim_permissions_supports_permissions_claim_and_client_roles(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "agenticai-web")

    assert auth._claims_have_permission(
        {"permissions": ["collection:create"]},
        "collection:create",
    )
    assert auth._claims_have_permission(
        {"resource_access": {"agenticai-web": {"roles": ["document:read"]}}},
        "document:read",
    )
    assert auth._claims_have_permission(
        {"realm_access": {"roles": ["*"]}}, "graph:read"
    )


# --------------------------------------------------------------------------
# resolve_user
# --------------------------------------------------------------------------


async def test_resolves_gateway_authenticated_user():
    user = await auth.resolve_user(
        request=_request(_gateway_headers()),
        credentials=_credentials("forwarded-user-token"),
    )

    assert user.identity == "keycloak-sub-1"
    assert user.display_name == "ada@example.com"
    assert user.access_token == "forwarded-user-token"
    assert user.claims["realm_access"]["roles"] == ["enduser"]


async def test_rejects_bare_keycloak_token():
    """A valid user JWT that did not come through Gateway is rejected."""
    with pytest.raises(UnauthorizedError) as exc:
        await auth.resolve_user(
            request=_request({"authorization": "Bearer real.jwt.token"}),
            credentials=_credentials("real.jwt.token"),
        )

    assert exc.value.status_code == 401


async def test_rejects_forged_gateway_user_id():
    headers = _gateway_headers()
    headers.pop("x-gateway-token")

    with pytest.raises(UnauthorizedError) as exc:
        await auth.resolve_user(request=_request(headers), credentials=None)

    assert exc.value.status_code == 401


async def test_rejects_anonymous_request():
    with pytest.raises(UnauthorizedError) as exc:
        await auth.resolve_user(request=_request(), credentials=None)

    assert exc.value.status_code == 401


async def test_rejects_non_bearer_scheme():
    with pytest.raises(UnauthorizedError) as exc:
        await auth.resolve_user(
            request=_request(_gateway_headers()),
            credentials=SimpleNamespace(scheme="Basic", credentials="x"),
        )

    assert exc.value.status_code == 401


async def test_accepts_internal_service_token():
    user = await auth.resolve_user(
        request=_request({"x-internal-service-token": SECRET}),
        credentials=None,
    )

    assert user.identity == "internal-service"


async def test_fails_closed_without_configured_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "")

    with pytest.raises(UnauthorizedError) as exc:
        await auth.resolve_user(request=_request(_gateway_headers()), credentials=None)

    assert exc.value.status_code == 401


async def test_no_dev_user_path_exists():
    """There is no code path that yields the old anonymous dev identity."""
    import inspect

    source = inspect.getsource(auth)
    assert "dev-user" not in source
