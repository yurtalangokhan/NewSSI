"""Bearer token authentication for the FastMCP HTTP transport."""

from __future__ import annotations

import os
import time
from typing import Any

import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier
from jwt import InvalidTokenError, PyJWKClient

from .authorization import get_user_service_permissions


def _get_valid_api_keys() -> set:
    keys = os.environ.get("VALID_API_KEYS", "")
    if keys:
        return {k.strip() for k in keys.split(",") if k.strip()}
    return set()


def _get_internal_service_token() -> str:
    return (os.environ.get("INTERNAL_SERVICE_TOKEN") or "").strip()


class KeycloakTokenVerifier(TokenVerifier):
    """Validate Bearer tokens for direct MCP access.

    Supports three authentication tiers checked in order:
    1. Keycloak RS256 JWT (if KEYCLOAK_ISSUER_URL is set)
    2. Internal Service Token (X-Internal-Service-Token header)
    3. VALID_API_KEYS (comma-separated in env)
    """

    def __init__(self) -> None:
        base_url = os.environ.get("MCP_PUBLIC_BASE_URL") or os.environ.get(
            "TOOLS_SERVICE_URL",
            "http://localhost:8003/mcp",
        )
        super().__init__(base_url=base_url, required_scopes=["tool:execute"])
        self._issuer = (os.environ.get("KEYCLOAK_ISSUER_URL") or "").rstrip("/")
        self._audience = os.environ.get("KEYCLOAK_AUDIENCE", "")
        self._client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "agenticai-web")
        self._leeway = int(os.environ.get("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "120"))
        self._jwks_client: PyJWKClient | None = None

    def _get_jwks_client(self) -> PyJWKClient | None:
        if not self._issuer:
            return None
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                f"{self._issuer}/protocol/openid-connect/certs",
                cache_keys=True,
            )
        return self._jwks_client

    def _audiences(self) -> list[str]:
        audiences = [a.strip() for a in self._audience.split(",") if a.strip()]
        if self._client_id and self._client_id not in audiences:
            audiences.append(self._client_id)
        return audiences

    async def verify_token(self, token: str) -> AccessToken | None:
        # Tier 1: Keycloak JWT validation
        jwks_client = self._get_jwks_client()
        if jwks_client is not None:
            audiences = self._audiences()
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                claims: dict[str, Any] = jwt.decode(
                    jwt=token,
                    key=signing_key.key,
                    algorithms=["RS256", "RS384", "RS512"],
                    issuer=self._issuer,
                    audience=audiences if audiences else None,
                    leeway=self._leeway,
                    options={
                        "verify_aud": bool(audiences),
                        "verify_iss": True,
                        "verify_exp": True,
                    },
                )
                subject = str(
                    claims.get("sub")
                    or claims.get("preferred_username")
                    or claims.get("email")
                    or ""
                )
                if subject:
                    exp = claims.get("exp")
                    expires_at = int(exp) if isinstance(exp, int) else int(time.time()) + 300
                    scopes = await get_user_service_permissions(token, subject)
                    return AccessToken(
                        token=token,
                        client_id=subject,
                        scopes=scopes,
                        expires_at=expires_at,
                        claims=claims,
                    )
            except InvalidTokenError:
                pass
            except Exception:
                pass

        # Tier 2: Internal Service Token (machine-to-machine)
        internal_token = _get_internal_service_token()
        if internal_token and token == internal_token:
            expires_at = int(time.time()) + 3600
            return AccessToken(
                token=token,
                client_id="internal-service",
                scopes=["tool:execute"],
                expires_at=expires_at,
                claims={"sub": "internal-service", "iss": "tools-service"},
            )

        # Tier 3: API key fallback
        valid_keys = _get_valid_api_keys()
        if token in valid_keys:
            expires_at = int(time.time()) + 3600
            return AccessToken(
                token=token,
                client_id=token,
                scopes=["tool:execute"],
                expires_at=expires_at,
                claims={"sub": token, "iss": "tools-service"},
            )

        # api-key:xxx format
        if token.startswith("api-key:"):
            key = token[8:]
            if key in valid_keys:
                expires_at = int(time.time()) + 3600
                return AccessToken(
                    token=token,
                    client_id=key,
                    scopes=["tool:execute"],
                    expires_at=expires_at,
                    claims={"sub": key, "iss": "tools-service"},
                )

        return None
