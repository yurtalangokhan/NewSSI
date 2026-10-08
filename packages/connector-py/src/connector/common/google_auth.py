"""Google API authentication shared by the Drive, Gmail and Sites sources.

Two ways to authenticate, in this order:

1. ``access_token`` – a ready OAuth2 token (short-lived; handy for tests and
   for callers that manage tokens themselves).
2. ``service_account_json`` – a service-account key. A JWT is signed with the
   key (RS256) and exchanged for a token. ``subject`` enables domain-wide
   delegation, which Gmail and "my drive" access require.

Signing needs the ``cryptography`` package (``pip install connector-py[google]``);
it is imported lazily so the rest of the package works without it.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..extras import require_extra
from .declarative import DeclarativeRestSource
from .oauth2 import OAuth2BearerMixin, OAuth2Token

ConfigT = TypeVar("ConfigT", bound="GoogleAuthConfig")

TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleAuthConfig(BaseModel):
    service_account_json: str | None = secret_field(
        default=None, description="Service-account key file content (JSON)."
    )
    subject: str | None = Field(
        default=None, description="User e-mail to impersonate (domain-wide delegation)."
    )
    access_token: str | None = secret_field(
        default=None, description="Pre-issued OAuth2 access token (alternative to the key)."
    )
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _one_credential(self) -> GoogleAuthConfig:
        if not self.service_account_json and not self.access_token:
            raise ValueError("either service_account_json or access_token is required")
        return self


class GoogleSource(OAuth2BearerMixin, DeclarativeRestSource[ConfigT]):
    """Declarative source that authenticates against Google APIs."""

    scopes: ClassVar[tuple[str, ...]] = ()

    def static_token(self) -> str | None:
        return self.config.access_token

    def oauth2_token(self) -> OAuth2Token:
        return OAuth2Token(TOKEN_URL, self._assertion_form)

    def _assertion_form(self) -> dict[str, Any]:
        # Built for every token request: the assertion is only valid for an hour.
        return {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": build_service_account_jwt(
                json.loads(self.config.service_account_json or "{}"),
                scopes=self.scopes,
                subject=self.config.subject,
            ),
        }


def build_service_account_jwt(
    key: dict[str, Any], *, scopes: tuple[str, ...], subject: str | None = None
) -> str:
    """Create the signed JWT assertion for the service-account token exchange."""
    primitives = "cryptography.hazmat.primitives"
    hashes = require_extra(f"{primitives}.hashes", extra="google", feature="google sources")
    serialization = require_extra(f"{primitives}.serialization", extra="google")
    padding = require_extra(f"{primitives}.asymmetric.padding", extra="google")

    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": key["client_email"],
        "scope": " ".join(scopes),
        "aud": key.get("token_uri", TOKEN_URL),
        "iat": now,
        "exp": now + 3600,
    }
    if subject:
        claims["sub"] = subject
    header = {"alg": "RS256", "typ": "JWT", "kid": key.get("private_key_id")}
    signing_input = f"{_b64(json.dumps(header))}.{_b64(json.dumps(claims))}"
    private_key = serialization.load_pem_private_key(key["private_key"].encode(), password=None)
    signature = private_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()
