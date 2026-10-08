"""Security mechanisms shared across services.

Each module here is a *mechanism*: it knows how to do one thing and has no
knowledge of which service called it. The bindings a service needs — its
``SecretScope`` names, its policy file location, its service name — live in that
service's ``src/core`` and are passed in.

Modules:

``secrets``
    Unwrapping ``pydantic.SecretStr``/``SecretBytes`` at the point of use.
``crypto``
    Scope-separated Fernet ciphers. Key validation is mandatory here, never in
    a caller.
``http`` / ``url_policy``
    SSRF-resistant outbound client, its connection pool, and the URL policy it
    enforces.
``resilience``
    Bounded retry, circuit breaking, and policy loading.
``gateway``
    Caller identity derived from headers that Gateway has already authenticated.
``tokens``
    JWKS-backed token verification.
``redaction``
    Masking secrets and internal identifiers out of text bound for a log or a
    model.
``cors``
    The origin/credential safety rule. Reading the configured origin list is
    configuration parsing and stays in ``config_manager``.
"""

from .cors import validate_cors_policy
from .crypto import FernetKeyError, ScopedCipherStore, mask_secret
from .gateway import (
    DELEGATED_USER_HEADER,
    GATEWAY_EMAIL_HEADER,
    GATEWAY_ROLES_HEADER,
    GATEWAY_ROUTE_PREFIXES,
    GATEWAY_TOKEN_HEADER,
    GATEWAY_USER_ID_HEADER,
    GATEWAY_USERNAME_HEADER,
    INTERNAL_SERVICE_EMAIL,
    INTERNAL_SERVICE_USER_ID,
    INTERNAL_TOKEN_HEADERS,
    GatewayIdentity,
    GatewayRoutingError,
    assert_gateway_routed,
    is_gateway_routed,
    resolve_gateway_identity,
)
from .http import (
    DEFAULT_LIMITS,
    DEFAULT_TIMEOUT,
    GuardedResponse,
    SecureHTTPClient,
    close_all,
    close_all_sync,
    get_shared_client,
    get_shared_sync_client,
)
from .redaction import MASKED, Redactor, redact_text
from .resilience import (
    TRANSIENT_HTTP_EXCEPTIONS,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    bounded_retry,
    get_circuit_breaker,
    load_resilience_config,
    reset_policy_cache,
    retry_for,
    retry_policy_for,
    retry_waits,
    timeout_for,
)
from .secrets import require_secret, reveal_secret
from .tokens import (
    DEFAULT_JWKS_URL_TEMPLATE,
    DynamicJwksVerifier,
    IdentityProviderUnavailableError,
    InvalidTokenError,
    JwksTokenVerifier,
    TokenVerificationError,
    decode_with_signing_key,
)
from .url_policy import (
    UrlPolicyError,
    is_blocked_ip,
    is_metadata_address,
    resolve_addresses,
    resolve_addresses_async,
    resolve_and_check,
    resolve_and_check_async,
    validate_url,
)

__all__ = [
    "DEFAULT_LIMITS",
    "DEFAULT_TIMEOUT",
    "DELEGATED_USER_HEADER",
    "GATEWAY_EMAIL_HEADER",
    "GATEWAY_ROUTE_PREFIXES",
    "GATEWAY_ROLES_HEADER",
    "GATEWAY_TOKEN_HEADER",
    "GATEWAY_USER_ID_HEADER",
    "GATEWAY_USERNAME_HEADER",
    "INTERNAL_SERVICE_EMAIL",
    "INTERNAL_SERVICE_USER_ID",
    "INTERNAL_TOKEN_HEADERS",
    "TRANSIENT_HTTP_EXCEPTIONS",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "FernetKeyError",
    "GatewayIdentity",
    "GatewayRoutingError",
    "GuardedResponse",
    "JwksTokenVerifier",
    "MASKED",
    "Redactor",
    "ScopedCipherStore",
    "SecureHTTPClient",
    "UrlPolicyError",
    "assert_gateway_routed",
    "bounded_retry",
    "close_all",
    "DEFAULT_JWKS_URL_TEMPLATE",
    "DynamicJwksVerifier",
    "IdentityProviderUnavailableError",
    "InvalidTokenError",
    "TokenVerificationError",
    "decode_with_signing_key",
    "close_all_sync",
    "get_circuit_breaker",
    "get_shared_client",
    "get_shared_sync_client",
    "is_blocked_ip",
    "is_metadata_address",
    "is_gateway_routed",
    "load_resilience_config",
    "mask_secret",
    "redact_text",
    "require_secret",
    "reset_policy_cache",
    "resolve_addresses",
    "resolve_addresses_async",
    "resolve_and_check",
    "resolve_and_check_async",
    "resolve_gateway_identity",
    "retry_for",
    "retry_policy_for",
    "retry_waits",
    "reveal_secret",
    "timeout_for",
    "validate_cors_policy",
    "validate_url",
]
