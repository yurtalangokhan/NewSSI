"""JWKS verification: audience handling and the refresh cooldown.

The cooldown is the behaviour worth pinning. Without it a token carrying a
garbage `kid` costs one identity-provider fetch per request, so an unreachable
provider becomes a self-inflicted outage.
"""

import jwt
import pytest

from security import JwksTokenVerifier

ISSUER = "https://keycloak.test/realms/main"


class FakeJwksClient:
    """Stands in for PyJWKClient, counting fetches and controlling failures."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def get_signing_key_from_jwt(self, token: str):
        self.calls += 1
        if self.fail:
            raise jwt.PyJWKClientError("no matching key")
        return type("Key", (), {"key": "signing-key"})()


def verifier(**kwargs) -> JwksTokenVerifier:
    return JwksTokenVerifier(ISSUER, **kwargs)


def test_jwks_url_is_derived_from_the_issuer():
    assert verifier()._jwks_url == f"{ISSUER}/protocol/openid-connect/certs"


def test_explicit_jwks_url_overrides_the_derived_one():
    v = verifier(jwks_url="https://elsewhere.test/certs")
    assert v._jwks_url == "https://elsewhere.test/certs"


def test_audiences_are_stripped_and_blank_entries_dropped():
    v = verifier(audiences=[" a ", "", "b"])
    assert v.audiences == ["a", "b"]


def test_client_is_cached():
    v = verifier()
    assert v.client() is v.client()


def test_refresh_replaces_the_client():
    v = verifier()
    first = v.client()
    assert v.refresh() is True
    assert v.client() is not first


def test_refresh_is_suppressed_inside_the_cooldown():
    """The second call must not reach the provider."""
    v = verifier(refresh_cooldown_seconds=60.0)
    assert v.refresh() is True
    assert v.refresh() is False


def test_refresh_is_allowed_once_the_cooldown_elapses():
    v = verifier(refresh_cooldown_seconds=0.0)
    assert v.refresh() is True
    assert v.refresh() is True


def test_a_failed_refresh_still_counts_against_the_window(monkeypatch):
    """An unreachable provider must not be re-dialled once per request.

    The window is consumed by the *attempt*, so a construction failure does not
    buy the next request a fresh fetch.
    """

    def explode(*args, **kwargs):
        raise OSError("provider unreachable")

    monkeypatch.setattr("security.tokens.PyJWKClient", explode)
    v = verifier(refresh_cooldown_seconds=60.0)
    assert v.refresh() is False
    assert v.refresh() is False


def test_signing_key_returns_the_key_without_refreshing_when_known():
    v = verifier()
    fake = FakeJwksClient()
    v._client = fake
    assert v.signing_key("t").key == "signing-key"
    assert fake.calls == 1


def test_signing_key_refreshes_once_on_an_unknown_kid(monkeypatch):
    """A rotated key is picked up by one refresh, then the retry succeeds."""
    calls = {"n": 0}

    class Rotating(FakeJwksClient):
        def get_signing_key_from_jwt(self, token: str):
            calls["n"] += 1
            if calls["n"] == 1:
                raise jwt.PyJWKClientError("no matching key")
            return type("Key", (), {"key": "rotated"})()

    monkeypatch.setattr("security.tokens.PyJWKClient", lambda *a, **k: Rotating())
    v = verifier(refresh_cooldown_seconds=0.0)
    assert v.signing_key("t").key == "rotated"
    assert calls["n"] == 2


def test_signing_key_raises_when_the_cooldown_blocks_a_retry(monkeypatch):
    """A garbage kid inside the window fails fast instead of fetching again."""
    monkeypatch.setattr("security.tokens.PyJWKClient", lambda *a, **k: FakeJwksClient(fail=True))
    v = verifier(refresh_cooldown_seconds=60.0)
    v.refresh()  # consume the window
    with pytest.raises(jwt.PyJWKClientError):
        v.signing_key("t")


def test_verify_skips_audience_check_when_none_is_configured(monkeypatch):
    """An empty audience list must mean "unconstrained", not "reject all"."""
    captured = {}

    def fake_decode(**kwargs):
        captured.update(kwargs)
        return {"sub": "user-1"}

    monkeypatch.setattr(jwt, "decode", fake_decode)
    v = verifier()
    v._client = FakeJwksClient()
    assert v.verify("t") == {"sub": "user-1"}
    assert captured["audience"] is None
    assert captured["options"]["verify_aud"] is False


def test_verify_enforces_audience_when_configured(monkeypatch):
    captured = {}

    def fake_decode(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(jwt, "decode", fake_decode)
    v = verifier(audiences=["agent-service"])
    v._client = FakeJwksClient()
    v.verify("t")
    assert captured["audience"] == ["agent-service"]
    assert captured["options"]["verify_aud"] is True


def test_verify_always_checks_issuer_and_expiry(monkeypatch):
    captured = {}
    monkeypatch.setattr(jwt, "decode", lambda **kw: captured.update(kw) or {})
    v = verifier()
    v._client = FakeJwksClient()
    v.verify("t")
    assert captured["issuer"] == ISSUER
    assert captured["options"]["verify_iss"] is True
    assert captured["options"]["verify_exp"] is True
