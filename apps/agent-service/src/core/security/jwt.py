"""Core JWT and Keycloak token verification infrastructure.

Lives in `core.security` as a foundational service with zero external layer
dependencies.

What stays here is this service's Keycloak policy: which issuer to trust, which
audiences a token may carry, how much clock skew to allow, and how long to
debounce a JWKS refresh. The verification mechanism itself — fetch a JWKS, cache
it, retry once on an unknown ``kid``, then check signature, issuer, expiry and
audience — is the `security` package's, because every service that trusts an
OIDC provider needs the same one and a second copy would drift.
"""

from __future__ import annotations

from typing import Any

from config_manager import env
from jwt import PyJWKClient
from localization import t
from security import (
    IdentityProviderUnavailableError,
    InvalidTokenError,
    JwksTokenVerifier,
)

from core.exceptions import DependencyUnavailableError, UnauthorizedError

#: A token whose ``kid`` Keycloak has never issued must not turn agent-service's
#: own request rate into an equal rate of JWKS fetches against Keycloak. One
#: refresh per window is enough: a genuine key rotation is picked up on the
#: first miss after the cooldown.
JWKS_REFRESH_COOLDOWN_SECONDS = 30.0

_verifier: JwksTokenVerifier | None = None


def get_keycloak_issuer() -> str:
    """Return the configured Keycloak issuer URL, stripped of trailing slashes."""
    issuer = (env.KEYCLOAK_ISSUER_URL or "").strip()
    if not issuer:
        raise DependencyUnavailableError(
            message=t("auth.keycloak_not_configured"),
            details={"dependency": "keycloak"},
        )
    return issuer.rstrip("/")


def get_keycloak_base_url() -> str:
    """Return the base Keycloak URL (without /realms/...)."""
    base_url = (env.KEYCLOAK_BASE_URL or "").rstrip("/")
    if not base_url:
        issuer = get_keycloak_issuer()
        if "/realms/" in issuer:
            base_url = issuer.split("/realms/")[0].rstrip("/")
    return base_url


def get_keycloak_realm() -> str:
    """Extract the realm name from the issuer URL."""
    issuer = get_keycloak_issuer()
    if "/realms/" in issuer:
        return issuer.split("/realms/")[1].strip("/")
    return "master"


def _audiences() -> list[str]:
    """The audiences a Keycloak token may carry for this service.

    The client ID is accepted as well as the explicit audience list: a token
    minted for this service's own client carries the client ID in ``aud``, and
    rejecting it would lock out the service's own legitimate callers.
    """
    raw = env.KEYCLOAK_AGENT_SERVICE_AUDIENCE or ""
    audiences = [a.strip() for a in raw.split(",") if a.strip()]
    client_id = env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID or ""
    if client_id and client_id not in audiences:
        audiences.append(client_id)
    return audiences


def get_verifier() -> JwksTokenVerifier:
    """The verifier for this service's Keycloak issuer.

    Built on first use rather than at import: an unconfigured Keycloak must not
    make the module unimportable, and the issuer is configuration that tests
    vary.
    """
    global _verifier
    if _verifier is None:
        _verifier = JwksTokenVerifier(
            get_keycloak_issuer(),
            audiences=_audiences(),
            leeway_seconds=env.KEYCLOAK_TOKEN_LEEWAY_SECONDS,
            refresh_cooldown_seconds=JWKS_REFRESH_COOLDOWN_SECONDS,
        )
    return _verifier


def reset_verifier() -> None:
    """Drop the cached verifier. For tests that vary the Keycloak configuration."""
    global _verifier
    _verifier = None


def get_jwks_client() -> PyJWKClient:
    """Return a cached PyJWKClient instance for token verification."""
    return get_verifier().client()


def refresh_jwks() -> bool:
    """Refresh the JWKS, at most once per cooldown window.

    Returns whether a refresh actually happened. ``False`` means the window has
    not elapsed — the caller should treat the key as genuinely unknown rather
    than retrying, which is what used to hand a garbage-``kid`` client one free
    Keycloak fetch per request. A failed attempt counts against the window too:
    an unreachable Keycloak must not be re-dialled once per request either.
    """
    return get_verifier().refresh()


def _translate(exc: Exception) -> Exception:
    """Map a verification failure onto this service's error contract.

    The package distinguishes the two outcomes; this is where they become a 503
    and a 401, and where the messages are translated. A provider outage must
    not be reported to a caller as an invalid token, because the caller's
    correct response to those two is different.
    """
    if isinstance(exc, IdentityProviderUnavailableError):
        return DependencyUnavailableError(
            message=t("auth.signing_key_resolution_failed", error=str(exc)),
            details={"dependency": "keycloak"},
        )
    return UnauthorizedError(message=t("auth.token_validation_failed"))


def get_signing_key(token: str) -> Any:
    """Get signing key for a JWT, with key rotation support."""
    try:
        return get_verifier().signing_key(token)
    except (InvalidTokenError, IdentityProviderUnavailableError) as exc:
        raise _translate(exc) from exc


def decode_keycloak_token(token: str) -> dict[str, Any]:
    """Decode and validate a Keycloak-issued JWT."""
    try:
        return get_verifier().verify(token)
    except (InvalidTokenError, IdentityProviderUnavailableError) as exc:
        raise _translate(exc) from exc
