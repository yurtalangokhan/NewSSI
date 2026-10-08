"""JWKS verification against an issuer that can change at runtime.

The point of this class is that a service whose identity provider is
reconfigurable — an admin pointing it at an external realm, a tenant setting —
does not have to keep its own copy of the verification rules, and does not have
to pretend an unreachable provider means the token was bad.
"""

from __future__ import annotations

import asyncio

import jwt
import pytest

from security import (
    DynamicJwksVerifier,
    IdentityProviderUnavailableError,
    InvalidTokenError,
    TokenVerificationError,
)

ISSUER = "https://issuer.test/realms/agent"
CERTS = f"{ISSUER}/protocol/openid-connect/certs"


class FakeKey:
    def __init__(self, kid: str = "k1") -> None:
        self.key = "signing-key"
        self.kid = kid


class FakeClient:
    """Stands in for PyJWKClient: serves known kids, fails like the real one."""

    instances: list[FakeClient] = []
    known: set[str] = {"k1"}
    fail_with: type[Exception] | None = None

    def __init__(self, jwks_url: str, *, cache_keys: bool = True) -> None:
        self.jwks_url = jwks_url
        FakeClient.instances.append(self)

    def get_signing_key_from_jwt(self, token: str) -> FakeKey:
        if FakeClient.fail_with is not None:
            raise FakeClient.fail_with("boom")
        kid = token.split(".")[0]
        if kid not in FakeClient.known:
            raise jwt.PyJWKClientError("Unable to find a signing key that matches: " + kid)
        return FakeKey(kid)


@pytest.fixture
def verifier(monkeypatch):
    FakeClient.instances = []
    FakeClient.known = {"k1"}
    FakeClient.fail_with = None
    monkeypatch.setattr("security.tokens.PyJWKClient", FakeClient)
    v = DynamicJwksVerifier(lambda: ISSUER, refresh_cooldown_seconds=60.0)
    yield v
    v.reset()


# --- the issuer is configuration, not a constant ----------------------------


async def test_the_issuer_is_resolved_on_every_verification(verifier, monkeypatch):
    assert verifier.issuer() == ISSUER

    current = ISSUER
    monkeypatch.setattr(verifier, "_resolve_issuer", lambda: current)
    current = "https://other.test/realms/agent"
    assert verifier.issuer() == "https://other.test/realms/agent"
    assert verifier.jwks_url(verifier.issuer()) == (
        "https://other.test/realms/agent/protocol/openid-connect/certs"
    )


async def test_a_missing_issuer_is_a_provider_problem_not_a_bad_token(verifier, monkeypatch):
    """Returning "no claims" here would be indistinguishable from a bad token."""
    monkeypatch.setattr(verifier, "_resolve_issuer", lambda: None)
    with pytest.raises(IdentityProviderUnavailableError, match="No identity provider issuer"):
        await verifier.signing_key("k1.any.sig")


async def test_an_unreachable_provider_is_not_reported_as_an_invalid_token(verifier):
    FakeClient.fail_with = jwt.PyJWKClientConnectionError
    with pytest.raises(IdentityProviderUnavailableError, match="Could not reach the JWKS"):
        await verifier.signing_key("k1.any.sig")


async def test_a_genuinely_unknown_key_is_an_invalid_token(verifier):
    with pytest.raises(InvalidTokenError, match="not found after JWKS refresh"):
        await verifier.signing_key("nope.any.sig")


async def test_the_error_types_share_a_base_so_callers_can_catch_either(verifier):
    for error in (InvalidTokenError, IdentityProviderUnavailableError):
        assert issubclass(error, TokenVerificationError)


# --- client state is per issuer and bounded ----------------------------------


async def test_clients_are_cached_per_issuer(verifier, monkeypatch):
    await verifier.signing_key("k1.a.sig")
    await verifier.signing_key("k1.b.sig")
    assert len(FakeClient.instances) == 1

    current = "https://second.test/realms/agent"
    monkeypatch.setattr(verifier, "_resolve_issuer", lambda: current)
    await verifier.signing_key("k1.c.sig")
    assert len(FakeClient.instances) == 2
    assert verifier.cached_issuers == [ISSUER, "https://second.test/realms/agent"]


async def test_the_client_cache_is_bounded(verifier, monkeypatch):
    """A misconfiguration that cycles issuers must not grow memory forever."""
    v = DynamicJwksVerifier(
        lambda: "https://i0.test/realms/r", max_cached_issuers=2, refresh_cooldown_seconds=0.0
    )
    for i in range(5):
        monkeypatch.setattr(v, "_resolve_issuer", lambda i=i: f"https://i{i}.test/realms/r")
        await v.signing_key("k1.a.sig")
    assert len(v.cached_issuers) <= 2


async def test_concurrent_first_use_builds_one_client(verifier):
    """Two concurrent first requests must not each construct a client."""
    await asyncio.gather(*(verifier.signing_key("k1.a.sig") for _ in range(8)))
    assert len(FakeClient.instances) == 1


async def test_reset_forgets_clients_and_cooldowns(verifier):
    await verifier.signing_key("k1.a.sig")
    assert verifier.cached_issuers == [ISSUER]
    verifier.reset()
    assert verifier.cached_issuers == []


# --- the refresh cooldown, per issuer ----------------------------------------


async def test_a_bad_kid_refreshes_only_once_within_the_cooldown(verifier):
    for _ in range(5):
        with pytest.raises(InvalidTokenError):
            await verifier.signing_key("nope.any.sig")
    # The initial client, plus one replacement for the first refresh-on-miss.
    assert len(FakeClient.instances) == 2


async def test_a_real_key_rotation_is_picked_up_once_the_cooldown_elapses(verifier):
    with pytest.raises(InvalidTokenError):
        await verifier.signing_key("nope.any.sig")

    FakeClient.known = {"k1", "k2"}
    verifier._last_refresh[ISSUER] -= 61.0
    assert (await verifier.signing_key("k2.a.sig")).kid == "k2"


async def test_the_cooldown_is_tracked_per_issuer(verifier, monkeypatch):
    """A miss on one realm must not debounce another realm."""
    current = "https://second.test/realms/agent"
    monkeypatch.setattr(verifier, "_resolve_issuer", lambda: current)
    with pytest.raises(InvalidTokenError):
        await verifier.signing_key("nope.a.sig")
    assert list(verifier._last_refresh) == ["https://second.test/realms/agent"]


# --- audiences and decoding ---------------------------------------------------


async def test_audiences_are_resolved_per_call(verifier, monkeypatch):
    captured: list[dict] = []

    def fake_decode(*, jwt, key, algorithms, issuer, audience, leeway, options):
        captured.append({"audience": audience, "issuer": issuer})
        return {"sub": "x"}

    monkeypatch.setattr("security.tokens.jwt.decode", fake_decode)
    current = ["one"]
    monkeypatch.setattr(verifier, "_resolve_audiences", lambda: current)

    await verifier.verify("k1.a.sig")
    current = ["one", "two"]
    await verifier.verify("k1.a.sig")

    assert [c["audience"] for c in captured] == [["one"], ["one", "two"]]


async def test_blank_audiences_are_dropped(verifier, monkeypatch):
    monkeypatch.setattr(verifier, "_resolve_audiences", lambda: [" a ", "", "  ", "b"])
    assert verifier._audiences_now() == ["a", "b"]


async def test_no_resolver_means_no_audiences(verifier):
    assert verifier._audiences_now() == []
