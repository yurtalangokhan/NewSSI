"""Caller identity from Gateway headers, and the fail-closed rule."""

from security import (
    GATEWAY_EMAIL_HEADER,
    GATEWAY_ROLES_HEADER,
    GATEWAY_TOKEN_HEADER,
    GATEWAY_USER_ID_HEADER,
    GATEWAY_USERNAME_HEADER,
    INTERNAL_SERVICE_USER_ID,
    resolve_gateway_identity,
)

SECRET = "shared-gateway-secret"


def gateway_headers(**overrides: str) -> dict[str, str]:
    headers = {
        GATEWAY_TOKEN_HEADER: SECRET,
        GATEWAY_USER_ID_HEADER: "user-1",
        GATEWAY_EMAIL_HEADER: "user@example.com",
        GATEWAY_USERNAME_HEADER: "user",
        GATEWAY_ROLES_HEADER: "Admin, viewer",
    }
    headers.update(overrides)
    return headers


def test_resolves_a_gateway_authenticated_caller():
    identity = resolve_gateway_identity(gateway_headers(), SECRET)
    assert identity is not None
    assert identity.user_id == "user-1"
    assert identity.email == "user@example.com"
    assert identity.username == "user"
    assert identity.roles == ("admin", "viewer")
    assert identity.is_internal is False


def test_header_lookup_is_case_insensitive():
    headers = {k.upper(): v for k, v in gateway_headers().items()}
    assert resolve_gateway_identity(headers, SECRET) is not None


def test_wrong_secret_is_untrusted():
    assert resolve_gateway_identity(gateway_headers(), "not-the-secret") is None


def test_unset_secret_fails_closed():
    """An unconfigured service must not trust arbitrary headers."""
    assert resolve_gateway_identity(gateway_headers(), None) is None
    assert resolve_gateway_identity(gateway_headers(), "") is None
    assert resolve_gateway_identity(gateway_headers(), "   ") is None


def test_missing_token_header_is_untrusted():
    headers = gateway_headers()
    del headers[GATEWAY_TOKEN_HEADER]
    assert resolve_gateway_identity(headers, SECRET) is None


def test_token_without_a_user_id_is_untrusted():
    assert resolve_gateway_identity(gateway_headers(**{GATEWAY_USER_ID_HEADER: ""}), SECRET) is None


def test_internal_token_yields_the_internal_identity():
    headers = {"x-internal-service-token": SECRET, "x-user-id": "delegated-9"}
    identity = resolve_gateway_identity(headers, SECRET)
    assert identity is not None
    assert identity.user_id == INTERNAL_SERVICE_USER_ID
    assert identity.is_internal is True
    assert identity.delegated_user_id == "delegated-9"
    assert identity.roles == ("internal",)


def test_internal_token_without_delegation_has_no_delegated_user():
    identity = resolve_gateway_identity({"x-internal-token": SECRET}, SECRET)
    assert identity is not None
    assert identity.delegated_user_id is None


def test_blank_username_becomes_none():
    identity = resolve_gateway_identity(gateway_headers(**{GATEWAY_USERNAME_HEADER: "  "}), SECRET)
    assert identity is not None
    assert identity.username is None


def test_blank_roles_become_an_empty_tuple():
    identity = resolve_gateway_identity(gateway_headers(**{GATEWAY_ROLES_HEADER: " , "}), SECRET)
    assert identity is not None
    assert identity.roles == ()
