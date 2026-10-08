"""Unit tests for core.security.jwt."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from security import IdentityProviderUnavailableError, InvalidTokenError

from core.exceptions import DependencyUnavailableError, UnauthorizedError
from core.security import jwt as jwt_module
from core.security.jwt import (
    get_keycloak_base_url,
    get_keycloak_realm,
)


def test_keycloak_helpers():
    # Calling functions to ensure no syntax/runtime issues with config defaults
    base_url = get_keycloak_base_url()
    assert isinstance(base_url, str)
    realm = get_keycloak_realm()
    assert isinstance(realm, str)


# --- the error contract the shared verifier's types are translated into ------
#
# The package raises typed errors; this service answers with a 503 or a 401.
# Losing that mapping is silent — a provider outage starts answering 401, and
# nothing fails until someone reads the logs.


def _verifier_raising(exc: Exception):
    verifier = Mock()
    verifier.signing_key.side_effect = exc
    verifier.verify.side_effect = exc
    return verifier


def test_an_invalid_token_is_unauthorized(monkeypatch):
    monkeypatch.setattr(jwt_module, "get_verifier", lambda: _verifier_raising(InvalidTokenError("nope")))

    with pytest.raises(UnauthorizedError):
        jwt_module.decode_keycloak_token("token")

    with pytest.raises(UnauthorizedError):
        jwt_module.get_signing_key("token")


def test_an_unreachable_keycloak_is_a_dependency_failure_not_unauthorized(monkeypatch):
    """A 401 here would tell the caller to re-authenticate against a broken IdP."""
    monkeypatch.setattr(
        jwt_module,
        "get_verifier",
        lambda: _verifier_raising(IdentityProviderUnavailableError("jwks unreachable")),
    )

    with pytest.raises(DependencyUnavailableError):
        jwt_module.decode_keycloak_token("token")

    with pytest.raises(DependencyUnavailableError):
        jwt_module.get_signing_key("token")


def test_the_failure_messages_are_translated(monkeypatch):
    from localization import t

    monkeypatch.setattr(jwt_module, "get_verifier", lambda: _verifier_raising(InvalidTokenError("nope")))
    with pytest.raises(UnauthorizedError) as invalid:
        jwt_module.decode_keycloak_token("token")
    assert t("auth.token_validation_failed") in str(invalid.value)

    monkeypatch.setattr(
        jwt_module,
        "get_verifier",
        lambda: _verifier_raising(IdentityProviderUnavailableError("jwks unreachable")),
    )
    with pytest.raises(DependencyUnavailableError) as unavailable:
        jwt_module.decode_keycloak_token("token")
    assert t("auth.signing_key_resolution_failed", error="jwks unreachable") in str(
        unavailable.value
    )
