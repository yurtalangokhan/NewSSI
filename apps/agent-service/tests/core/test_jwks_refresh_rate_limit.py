"""A stream of tokens with an unrecognised `kid` must not hammer Keycloak.

The debounce itself is the `security` package's and is tested there. What is
agent-service's own — and therefore what this module pins — is the wiring: that
the cooldown this service chose is the one handed to the verifier, that the
verifier trusts the configured issuer, and that a garbage-``kid`` client still
gets only one extra Keycloak fetch per window through this entry point.

The refresh path used to live in ``service.auth``; Gateway owns request
authentication now and the JWKS code lives in ``core.security.jwt``, so the
guard follows it.
"""

from __future__ import annotations

import jwt
import pytest

from core.security import jwt as jwt_module
from core.security.jwt import (
    JWKS_REFRESH_COOLDOWN_SECONDS,
    get_signing_key,
    get_verifier,
)


class _AlwaysMissingKidClient:
    instances = 0

    def __init__(self, jwks_url: str, *, cache_jwk_set: bool = True) -> None:
        _AlwaysMissingKidClient.instances += 1

    def get_signing_key_from_jwt(self, token: str):
        raise jwt.PyJWKClientError("Unable to find a signing key that matches: none")


@pytest.fixture
def verifier(monkeypatch):
    """A verifier bound to a fixed fake JWKS endpoint, with no cached state."""
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://keycloak.test/realms/agent")
    monkeypatch.setenv("KEYCLOAK_AGENT_SERVICE_AUDIENCE", "account, agent-api")
    monkeypatch.setenv("KEYCLOAK_AGENT_SERVICE_CLIENT_ID", "agent-service-client")
    monkeypatch.setenv("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "5")
    monkeypatch.setattr(
        "security.tokens.PyJWKClient", _AlwaysMissingKidClient
    )
    _AlwaysMissingKidClient.instances = 0
    jwt_module.reset_verifier()
    yield get_verifier()
    jwt_module.reset_verifier()


def test_the_service_chooses_its_own_cooldown():
    """The package default is 60s; this service's documented value is 30s."""
    assert JWKS_REFRESH_COOLDOWN_SECONDS == 30.0


def test_the_verifier_trusts_the_configured_issuer(verifier):
    assert (
        verifier.jwks_url
        == "https://keycloak.test/realms/agent/protocol/openid-connect/certs"
    )


def test_the_client_id_is_accepted_alongside_the_configured_audiences(verifier):
    assert verifier.audiences == ["account", "agent-api", "agent-service-client"]


def test_repeated_bad_kids_only_refresh_the_jwks_once_within_the_cooldown(verifier):
    for _ in range(5):
        with pytest.raises(jwt.PyJWKClientError):
            get_signing_key("irrelevant-token")

    # One instantiation for the initial lazy client, one for the first
    # refresh-on-miss. The next four misses arrive inside the cooldown
    # window and must not trigger four more Keycloak fetches.
    assert _AlwaysMissingKidClient.instances == 2


def test_the_verifier_is_rebuilt_after_the_keycloak_configuration_changes(monkeypatch):
    """Runtime reconfiguration must not be answered by a stale cached issuer."""
    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://first.test/realms/agent")
    monkeypatch.setenv("KEYCLOAK_AGENT_SERVICE_AUDIENCE", "a")
    monkeypatch.setenv("KEYCLOAK_AGENT_SERVICE_CLIENT_ID", "")
    jwt_module.reset_verifier()
    assert get_verifier().audiences == ["a"]

    monkeypatch.setenv("KEYCLOAK_ISSUER_URL", "https://second.test/realms/agent")
    jwt_module.reset_verifier()
    assert get_verifier().jwks_url == (
        "https://second.test/realms/agent/protocol/openid-connect/certs"
    )
