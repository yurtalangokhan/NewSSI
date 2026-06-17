"""Bearer token authentication for the FastMCP HTTP transport."""

from __future__ import annotations

import os
import time
from typing import Any

import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier
from jwt import InvalidTokenError, PyJWKClient


class KeycloakTokenVerifier(TokenVerifier):
    """Validate Keycloak-issued Bearer tokens for direct MCP access."""

    def __init__(self) -> None:
        base_url = os.environ.get("MCP_PUBLIC_BASE_URL") or os.environ.get(
            "TOOLS_SERVICE_URL",
            "http://localhost:8003/mcp",
        )
        super().__init__(base_url=base_url)
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
        jwks_client = self._get_jwks_client()
        if jwks_client is None:
            return None

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
        except InvalidTokenError:
            return None
        except Exception:
            return None

        subject = str(
            claims.get("sub")
            or claims.get("preferred_username")
            or claims.get("email")
            or ""
        )
        if not subject:
            return None

        exp = claims.get("exp")
        expires_at = int(exp) if isinstance(exp, int) else int(time.time()) + 300
        return AccessToken(
            token=token,
            client_id=subject,
            scopes=[],
            expires_at=expires_at,
            claims=claims,
        )
