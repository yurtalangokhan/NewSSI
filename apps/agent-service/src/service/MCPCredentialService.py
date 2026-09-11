"""MCP credential service — encrypted storage + header resolution for MCP auth.

Owns everything secret about an external MCP provider:

* admin/shared and per-user credentials (API keys, OAuth client id/secret),
* per-user OAuth access/refresh tokens,
* turning a provider row + a user id into the HTTP headers needed to reach the
  server (bearer token / templated API key / nothing), refreshing an expiring
  OAuth token inline.

Ciphertext lives in ``mcp_provider_auth`` via :class:`MCPProviderAuthRepository`;
plaintext never leaves this module except through :meth:`resolve_headers` /
:meth:`get_credentials`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from core.db.repositories import MCPProviderAuthRepository
from core.env import env
from core.logger import get_logger
from core.mcp_enums import MCPAuthPerformer, MCPAuthType
from core.security.encryption import decrypt_secret, encrypt_secret, mask_api_key

logger = get_logger(__name__)

# Refresh an OAuth token this many seconds before it actually expires.
_REFRESH_SKEW_SECONDS = 60


class MCPAuthError(Exception):
    """Raised when MCP auth cannot be resolved.

    The message always contains one of ``credentials`` / ``oauth`` /
    ``validation`` so the frontend ``errorMessageMap`` can classify it.
    """


class MCPCredentialService:
    """Encrypted credential + OAuth-token storage and header resolution."""

    _instance: MCPCredentialService | None = None

    def __init__(self, auth_repo: MCPProviderAuthRepository | None = None) -> None:
        self._repo = auth_repo or MCPProviderAuthRepository()

    @classmethod
    def get_instance(cls) -> MCPCredentialService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- encoding helpers -------------------------------------------------- #

    @staticmethod
    def _encrypt(value: str) -> str:
        return encrypt_secret(value)

    @staticmethod
    def _decrypt(value: str) -> str:
        return decrypt_secret(value)

    @staticmethod
    def _effective_user_id(provider_row: dict[str, Any], user_id: str | None) -> str | None:
        """``None`` means the admin/shared row."""
        if provider_row.get("auth_performer") == MCPAuthPerformer.ADMIN:
            return None
        return user_id

    # -- credential storage --------------------------------------------- #

    async def store_admin_credentials(self, provider_id: str, creds: dict[str, str]) -> None:
        await self._repo.upsert(
            provider_id,
            None,
            credentials_encrypted=self._encrypt(json.dumps(creds)),
        )

    async def store_user_credentials(
        self, provider_id: str, user_id: str, creds: dict[str, str]
    ) -> None:
        await self._repo.upsert(
            provider_id,
            user_id,
            credentials_encrypted=self._encrypt(json.dumps(creds)),
        )

    async def get_credentials(self, provider_id: str, user_id: str | None) -> dict[str, str]:
        row = await self._repo.get(provider_id, user_id)
        if not row or not row.get("credentials_encrypted"):
            return {}
        try:
            return json.loads(self._decrypt(row["credentials_encrypted"]))
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("could not decode MCP credentials for %s: %s", provider_id, exc)
            return {}

    # -- oauth token storage ------------------------------------------- #

    async def store_oauth_tokens(
        self,
        provider_id: str,
        user_id: str | None,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime | None,
        scopes: list[str] | None,
    ) -> None:
        await self._repo.upsert(
            provider_id,
            user_id,
            oauth_access_token_encrypted=self._encrypt(access_token),
            oauth_refresh_token_encrypted=(self._encrypt(refresh_token) if refresh_token else None),
            oauth_expires_at=expires_at,
            oauth_scopes=scopes,
        )

    async def get_oauth_tokens(
        self, provider_id: str, user_id: str | None
    ) -> dict[str, Any] | None:
        row = await self._repo.get(provider_id, user_id)
        if not row or not row.get("oauth_access_token_encrypted"):
            return None
        expires_raw = row.get("oauth_expires_at")
        expires_at = (
            datetime.fromisoformat(expires_raw) if isinstance(expires_raw, str) else expires_raw
        )
        return {
            "access_token": self._decrypt(row["oauth_access_token_encrypted"]),
            "refresh_token": (
                self._decrypt(row["oauth_refresh_token_encrypted"])
                if row.get("oauth_refresh_token_encrypted")
                else None
            ),
            "expires_at": expires_at,
        }

    # -- status ------------------------------------------------------- #

    async def has_valid_auth(self, provider_row: dict[str, Any], *, user_id: str | None) -> bool:
        auth_type = provider_row.get("auth_type", MCPAuthType.NONE)
        if auth_type == MCPAuthType.NONE:
            return True
        eff = self._effective_user_id(provider_row, user_id)
        if auth_type in (MCPAuthType.OAUTH, MCPAuthType.PT_OAUTH):
            tokens = await self.get_oauth_tokens(provider_row["id"], eff)
            return tokens is not None
        creds = await self.get_credentials(provider_row["id"], eff)
        return bool(creds)

    # -- header resolution ------------------------------------------ #

    async def resolve_headers(
        self,
        provider_row: dict[str, Any],
        *,
        user_id: str | None,
        passthrough_token: str | None = None,
    ) -> dict[str, str]:
        auth_type = provider_row.get("auth_type", MCPAuthType.NONE)
        if auth_type == MCPAuthType.NONE:
            return {}

        eff = self._effective_user_id(provider_row, user_id)

        if auth_type == MCPAuthType.API_TOKEN:
            return await self._api_token_headers(provider_row, eff)

        if auth_type == MCPAuthType.PT_OAUTH:
            if not passthrough_token:
                raise MCPAuthError("oauth pass-through token unavailable")
            return {"Authorization": f"Bearer {passthrough_token}"}

        if auth_type == MCPAuthType.OAUTH:
            return await self._oauth_headers(provider_row, eff)

        raise MCPAuthError(f"validation error: unknown auth_type {auth_type!r}")

    async def _api_token_headers(
        self, provider_row: dict[str, Any], eff_user_id: str | None
    ) -> dict[str, str]:
        creds = await self.get_credentials(provider_row["id"], eff_user_id)
        template = provider_row.get("auth_template")

        if template and template.get("headers"):
            for field in template.get("required_fields", []):
                if not creds.get(field):
                    raise MCPAuthError(f"credentials incomplete: missing {field}")
            try:
                return {k: v.format(**creds) for k, v in template["headers"].items()}
            except KeyError as exc:  # a placeholder with no matching credential
                raise MCPAuthError(f"credentials incomplete: missing {exc.args[0]}") from exc

        api_key = creds.get("api_key")
        if not api_key:
            raise MCPAuthError("credentials incomplete: missing api_key")
        return {"Authorization": f"Bearer {api_key}"}

    async def _oauth_headers(
        self, provider_row: dict[str, Any], eff_user_id: str | None
    ) -> dict[str, str]:
        tokens = await self.get_oauth_tokens(provider_row["id"], eff_user_id)
        if not tokens:
            raise MCPAuthError("oauth authorization required")

        access_token = tokens["access_token"]
        expires_at = tokens.get("expires_at")
        refresh_token = tokens.get("refresh_token")
        now = datetime.now(UTC)
        needs_refresh = expires_at is None or expires_at <= now + timedelta(
            seconds=_REFRESH_SKEW_SECONDS
        )

        if needs_refresh and refresh_token:
            try:
                new_access, new_refresh, new_expiry, scopes = await self._refresh_oauth_token(
                    provider_row, eff_user_id, refresh_token
                )
            except MCPAuthError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize to MCPAuthError
                raise MCPAuthError(f"oauth token refresh failed: {exc}") from exc
            await self.store_oauth_tokens(
                provider_row["id"],
                eff_user_id,
                access_token=new_access,
                refresh_token=new_refresh or refresh_token,
                expires_at=new_expiry,
                scopes=scopes,
            )
            access_token = new_access

        return {"Authorization": f"Bearer {access_token}"}

    async def _refresh_oauth_token(
        self, provider_row: dict[str, Any], eff_user_id: str | None, refresh_token: str
    ) -> tuple[str, str | None, datetime, list[str] | None]:
        metadata = provider_row.get("oauth_metadata") or {}
        token_endpoint = metadata.get("token_endpoint")
        if not token_endpoint:
            raise MCPAuthError("oauth token refresh failed: no token endpoint on record")

        client_creds = await self.get_credentials(provider_row["id"], None)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if client_creds.get("client_id"):
            data["client_id"] = client_creds["client_id"]
        if client_creds.get("client_secret"):
            data["client_secret"] = client_creds["client_secret"]

        async with httpx.AsyncClient(timeout=env.MCP_OAUTH_HTTP_TIMEOUT) as client:
            resp = await client.post(
                token_endpoint, data=data, headers={"Accept": "application/json"}
            )
        if not resp.is_success:
            raise MCPAuthError(f"oauth token refresh failed: {resp.text}")

        payload = resp.json()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=int(payload.get("expires_in", env.MCP_OAUTH_DEFAULT_TOKEN_TTL_SECONDS))
        )
        scopes = payload.get("scope", "").split() or None
        return (
            payload["access_token"],
            payload.get("refresh_token"),
            expires_at,
            scopes,
        )

    # -- misc ------------------------------------------------------- #

    @staticmethod
    def masked_credentials(creds: dict[str, str]) -> dict[str, str]:
        masked: dict[str, str] = {}
        for key, value in creds.items():
            if key == "client_id":
                masked[key] = value
            else:
                masked[key] = mask_api_key(value) if value else value
        return masked
