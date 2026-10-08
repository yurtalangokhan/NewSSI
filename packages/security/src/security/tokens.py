"""JWKS-backed token verification.

The mechanism — fetch a JWKS, cache it, retry once on an unknown ``kid`` under
a cooldown, then verify signature, issuer, expiry and audience — is the same for
every service that trusts the same identity provider. What differs is *which*
issuer, which audiences, and how much clock skew to allow, so those are
constructor arguments rather than configuration reads.

The cooldown is not an optimisation. Without it, a client holding a token with a
garbage ``kid`` triggers one Keycloak fetch per request; an unreachable Keycloak
turns into a self-inflicted denial of service. A failed refresh counts against
the window for the same reason.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import jwt
from cachetools import LRUCache
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

DEFAULT_REFRESH_COOLDOWN_SECONDS = 60.0
ACCEPTED_ALGORITHMS = ("RS256", "RS384", "RS512")


class JwksTokenVerifier:
    """Verifies tokens against a JWKS endpoint, with key-rotation support."""

    __slots__ = (
        "_audiences",
        "_client",
        "_cooldown",
        "_issuer",
        "_jwks_url",
        "_last_refresh",
        "_leeway",
    )

    def __init__(
        self,
        issuer: str,
        *,
        audiences: Sequence[str] = (),
        leeway_seconds: float = 0.0,
        refresh_cooldown_seconds: float = DEFAULT_REFRESH_COOLDOWN_SECONDS,
        jwks_url: str | None = None,
    ) -> None:
        self._issuer = issuer
        self._audiences = [a for a in (aud.strip() for aud in audiences) if a]
        self._leeway = leeway_seconds
        self._cooldown = refresh_cooldown_seconds
        self._client: PyJWKClient | None = None
        self._last_refresh = 0.0
        self._jwks_url = jwks_url or f"{issuer}/protocol/openid-connect/certs"

    @property
    def audiences(self) -> list[str]:
        return list(self._audiences)

    @property
    def jwks_url(self) -> str:
        """The endpoint this verifier trusts keys from."""
        return self._jwks_url

    def client(self) -> PyJWKClient:
        """Return the cached JWKS client, creating it on first use."""
        if self._client is None:
            self._client = PyJWKClient(self._jwks_url, cache_jwk_set=True)
        return self._client

    def refresh(self) -> bool:
        """Refresh the JWKS, at most once per cooldown window.

        Returns whether a refresh actually happened. ``False`` means the window
        has not elapsed, and the caller should treat the key as genuinely
        unknown rather than retrying.
        """
        now = time.monotonic()
        if now - self._last_refresh < self._cooldown:
            return False
        self._last_refresh = now
        try:
            self._client = None
            self.client()
            return True
        except Exception as exc:
            logger.warning("Failed to refresh JWKS client: %s", exc)
            return False

    def signing_key(self, token: str) -> Any:
        """Resolve a token's signing key, refreshing once if the `kid` is unknown."""
        try:
            return self.client().get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError as exc:
            if not self.refresh():
                raise
            try:
                return self.client().get_signing_key_from_jwt(token)
            except jwt.PyJWKClientError as refreshed_exc:
                logger.warning(
                    "Identity provider signing key not found after JWKS refresh: %s",
                    refreshed_exc,
                )
                raise exc from refreshed_exc

    def verify(self, token: str) -> dict[str, Any]:
        """Verify a token and return its claims."""
        return decode_with_signing_key(
            token,
            self.signing_key(token),
            issuer=self._issuer,
            audiences=self._audiences,
            leeway_seconds=self._leeway,
        )


def decode_with_signing_key(
    token: str,
    signing_key: Any,
    *,
    issuer: str,
    audiences: Sequence[str] = (),
    leeway_seconds: float = 0.0,
) -> dict[str, Any]:
    """Verify signature, issuer, expiry and audience against a resolved key.

    Separated from :class:`JwksTokenVerifier` so a caller that manages its own
    JWKS clients — a multi-issuer cache, say — still verifies tokens by exactly
    the same rules instead of keeping a second copy of them.

    Audience verification is skipped when no audience is configured, because
    requiring a match against an empty list would reject every token rather
    than accept an unconstrained one deliberately.
    """
    accepted = [a.strip() for a in audiences if a and a.strip()]
    return jwt.decode(
        jwt=token,
        key=signing_key.key if hasattr(signing_key, "key") else signing_key,
        algorithms=list(ACCEPTED_ALGORITHMS),
        issuer=issuer,
        audience=accepted or None,
        leeway=leeway_seconds,
        options={
            "verify_aud": bool(accepted),
            "verify_iss": True,
            "verify_exp": True,
            "verify_iat": False,
        },
    )


class TokenVerificationError(Exception):
    """Base: a token could not be verified.

    Callers that try several verification strategies in turn need to tell a
    strategy that says "no" from one that could not reach a verdict, so the two
    are separate types rather than a single falsy return.
    """


class InvalidTokenError(TokenVerificationError):
    """The token itself is not acceptable: bad signature, issuer, audience or expiry.

    This is a verdict, not a failure. A caller may reasonably move on to
    another strategy.
    """


class IdentityProviderUnavailableError(TokenVerificationError):
    """The identity provider could not be consulted, so the token was never checked.

    Distinct from :class:`InvalidTokenError` because treating an unreachable
    Keycloak as "invalid token" turns an outage into a wave of 401s and hides
    the outage entirely.
    """


DEFAULT_JWKS_URL_TEMPLATE = "{issuer}/protocol/openid-connect/certs"


class DynamicJwksVerifier:
    """JWKS verification against an issuer that can change while the process runs.

    For services whose identity provider is reconfigurable at runtime — tenant
    settings, an admin pointing the service at an external realm — rather than
    fixed at process start. The issuer, the accepted audiences and the clock
    skew are therefore resolved on each verification rather than captured once.

    Client state is kept per issuer in a bounded LRU: switching realms must not
    keep serving the previous one's clients, and must not grow without bound if
    a misconfiguration cycles through many issuers.
    """

    __slots__ = (
        "_audiences",
        "_cache_keys",
        "_clients",
        "_cooldown",
        "_last_refresh",
        "_leeway",
        "_lock",
        "_lock_loop",
        "_max_issuers",
        "_resolve_audiences",
        "_resolve_issuer",
        "_url_template",
    )

    def __init__(
        self,
        resolve_issuer: Callable[[], str | None],
        *,
        resolve_audiences: Callable[[], Sequence[str]] | None = None,
        leeway_seconds: float = 0.0,
        refresh_cooldown_seconds: float = DEFAULT_REFRESH_COOLDOWN_SECONDS,
        max_cached_issuers: int = 8,
        jwks_url_template: str = DEFAULT_JWKS_URL_TEMPLATE,
        cache_keys: bool = True,
    ) -> None:
        self._resolve_issuer = resolve_issuer
        self._resolve_audiences = resolve_audiences
        self._leeway = leeway_seconds
        self._cooldown = refresh_cooldown_seconds
        self._max_issuers = max_cached_issuers
        self._url_template = jwks_url_template
        self._cache_keys = cache_keys
        self._clients: LRUCache[str, PyJWKClient] = LRUCache(maxsize=max_cached_issuers)
        self._last_refresh: dict[str, float] = {}
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    def reset(self) -> None:
        """Forget every cached client and cooldown. Call after a config change."""
        self._clients.clear()
        self._last_refresh.clear()

    @property
    def cached_issuers(self) -> list[str]:
        return list(self._clients)

    def issuer(self) -> str:
        """The issuer to trust right now, or a clear error if it is not configured."""
        raw = self._resolve_issuer()
        issuer = (raw or "").strip().rstrip("/")
        if not issuer:
            raise IdentityProviderUnavailableError("No identity provider issuer is configured")
        return issuer

    def jwks_url(self, issuer: str) -> str:
        return self._url_template.format(issuer=issuer.rstrip("/"))

    def _audiences_now(self) -> list[str]:
        if self._resolve_audiences is None:
            return []
        return [a.strip() for a in self._resolve_audiences() if a and a.strip()]

    def _lock_for_loop(self) -> asyncio.Lock:
        """A lock bound to the running loop.

        Rebound when the loop changes so a process that runs more than one (tests,
        most often) does not reuse a lock that belongs to a dead loop.
        """
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    async def _client_for(self, issuer: str) -> PyJWKClient:
        client = self._clients.get(issuer)
        if client is not None:
            return client
        async with self._lock_for_loop():
            client = self._clients.get(issuer)
            if client is None:
                client = PyJWKClient(
                    self.jwks_url(issuer),
                    cache_keys=self._cache_keys,
                )
                self._clients[issuer] = client
        return client

    def _refresh_allowed(self, issuer: str) -> bool:
        now = time.monotonic()
        if now - self._last_refresh.get(issuer, 0.0) < self._cooldown:
            return False
        self._last_refresh[issuer] = now
        self._clients.pop(issuer, None)
        return True

    async def signing_key(self, token: str) -> Any:
        """Resolve a token's signing key, refreshing once if the `kid` is unknown."""
        issuer = self.issuer()
        client = await self._client_for(issuer)
        try:
            return client.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            raise IdentityProviderUnavailableError(
                f"Could not reach the JWKS endpoint for {issuer}"
            ) from exc
        except jwt.PyJWKClientError as exc:
            if not self._refresh_allowed(issuer):
                raise InvalidTokenError(
                    "Identity provider signing key not found, and a refresh was "
                    "recently attempted"
                ) from exc
            refreshed = await self._client_for(issuer)
            try:
                return refreshed.get_signing_key_from_jwt(token)
            except jwt.PyJWKClientError as refreshed_exc:
                raise InvalidTokenError(
                    "Identity provider signing key not found after JWKS refresh"
                ) from refreshed_exc

    async def verify(self, token: str) -> dict[str, Any]:
        """Verify a token against the currently configured issuer and audiences."""
        issuer = self.issuer()
        return decode_with_signing_key(
            token,
            await self.signing_key(token),
            issuer=issuer,
            audiences=self._audiences_now(),
            leeway_seconds=self._leeway,
        )


__all__ = [
    "ACCEPTED_ALGORITHMS",
    "DEFAULT_JWKS_URL_TEMPLATE",
    "DEFAULT_REFRESH_COOLDOWN_SECONDS",
    "DynamicJwksVerifier",
    "IdentityProviderUnavailableError",
    "InvalidTokenError",
    "JwksTokenVerifier",
    "TokenVerificationError",
    "decode_with_signing_key",
]
