"""MCP OAuth service — discovery, Dynamic Client Registration, PKCE, code exchange.

Implements the client half of the MCP authorization spec:

* RFC 9728 protected-resource metadata + RFC 8414 authorization-server metadata
  discovery (with a ``WWW-Authenticate`` fallback),
* RFC 7591 Dynamic Client Registration when the caller has no client id,
* RFC 7636 PKCE (S256) authorization-code flow,
* RFC 8707 ``resource`` parameter when requested.

Short-lived flow state lives in ``mcp_oauth_session``; resulting tokens are
handed to :class:`MCPCredentialService` for encrypted storage.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from core.db.repositories import MCPOAuthSessionRepository, MCPProviderRepository
from core.env import env
from core.logger import get_logger
from core.mcp_enums import MCPAuthPerformer, MCPServerStatus
from core.security.encryption import decrypt_secret, encrypt_secret
from service.MCPCredentialService import MCPAuthError, MCPCredentialService

__all__ = ["MCPOAuthService", "MCPAuthError"]

logger = get_logger(__name__)

# MCP spec revision advertised on the discovery probe request.
_MCP_PROTOCOL_VERSION = "2025-06-18"
# Path (under MCP_OAUTH_REDIRECT_BASE) the browser is redirected back to.
_OAUTH_CALLBACK_PATH = "/mcp/oauth/callback"
# Where the callback lands the admin when the flow carried no return path.
_DEFAULT_RETURN_PATH = "/admin/actions/mcp"


class MCPOAuthService:
    """Bootstraps and completes OAuth authorization-code flows for MCP servers."""

    _instance: MCPOAuthService | None = None

    def __init__(
        self,
        provider_repo: MCPProviderRepository | None = None,
        session_repo: MCPOAuthSessionRepository | None = None,
    ) -> None:
        self._provider_repo = provider_repo or MCPProviderRepository()
        self._session_repo = session_repo or MCPOAuthSessionRepository()

    @classmethod
    def get_instance(cls) -> MCPOAuthService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- helpers ------------------------------------------------------ #

    @staticmethod
    def _pkce_pair() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)[:128]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return verifier, challenge

    @staticmethod
    def _redirect_uri() -> str:
        return f"{env.MCP_OAUTH_REDIRECT_BASE.rstrip('/')}{_OAUTH_CALLBACK_PATH}"

    # -- discovery -------------------------------------------------- #

    async def discover(self, server_url: str) -> dict[str, Any]:
        parsed = urlparse(server_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.rstrip("/")

        async with httpx.AsyncClient(
            timeout=env.MCP_OAUTH_HTTP_TIMEOUT, follow_redirects=True
        ) as client:
            prm = await self._fetch_protected_resource_metadata(client, origin, path, server_url)
            if not prm or not prm.get("authorization_servers"):
                raise MCPAuthError("oauth discovery failed: no protected-resource metadata")

            as_url = str(prm["authorization_servers"][0]).rstrip("/")
            resource = prm.get("resource") or server_url

            asm = await self._fetch_first_json(
                client,
                [
                    f"{as_url}/.well-known/oauth-authorization-server",
                    f"{as_url}/.well-known/openid-configuration",
                ],
            )
        if not asm or not asm.get("authorization_endpoint") or not asm.get("token_endpoint"):
            raise MCPAuthError("oauth discovery failed: no authorization-server metadata")

        return {
            "authorization_endpoint": asm["authorization_endpoint"],
            "token_endpoint": asm["token_endpoint"],
            "registration_endpoint": asm.get("registration_endpoint"),
            "scopes_supported": asm.get("scopes_supported", []),
            "resource": resource,
            "discovered_at": datetime.now(UTC).isoformat(),
        }

    async def _fetch_protected_resource_metadata(
        self, client: httpx.AsyncClient, origin: str, path: str, server_url: str
    ) -> dict[str, Any] | None:
        candidates = [
            f"{origin}/.well-known/oauth-protected-resource{path}",
            f"{origin}/.well-known/oauth-protected-resource",
        ]
        doc = await self._fetch_first_json(client, candidates)
        if doc:
            return doc

        # Fallback: probe the MCP endpoint for a WWW-Authenticate hint.
        try:
            probe = await client.get(
                server_url,
                headers={
                    "MCP-Protocol-Version": _MCP_PROTOCOL_VERSION,
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError:
            return None
        if probe.status_code == 401:
            header = probe.headers.get("WWW-Authenticate", "")
            marker = 'resource_metadata="'
            if marker in header:
                meta_url = header.split(marker, 1)[1].split('"', 1)[0]
                return await self._fetch_first_json(client, [meta_url])
        return None

    @staticmethod
    async def _fetch_first_json(
        client: httpx.AsyncClient, urls: list[str]
    ) -> dict[str, Any] | None:
        for url in urls:
            try:
                resp = await client.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError:
                continue
            if resp.is_success:
                try:
                    return resp.json()
                except ValueError:
                    continue
        return None

    # -- client registration ------------------------------------- #

    async def ensure_client(
        self,
        provider_row: dict[str, Any],
        metadata: dict[str, Any],
        *,
        client_id: str | None,
        client_secret: str | None,
    ) -> tuple[str, str | None]:
        creds = MCPCredentialService.get_instance()

        if client_id:
            await creds.store_admin_credentials(
                provider_row["id"],
                {
                    "client_id": client_id,
                    **({"client_secret": client_secret} if client_secret else {}),
                },
            )
            return client_id, client_secret

        registration_endpoint = metadata.get("registration_endpoint")
        if not registration_endpoint:
            raise MCPAuthError(
                "server requires manual client registration; provide client id/secret"
            )

        body = {
            "client_name": env.MCP_OAUTH_CLIENT_NAME,
            "redirect_uris": [self._redirect_uri()],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        }
        async with httpx.AsyncClient(timeout=env.MCP_OAUTH_HTTP_TIMEOUT) as client:
            resp = await client.post(
                registration_endpoint, json=body, headers={"Accept": "application/json"}
            )
        if not resp.is_success:
            raise MCPAuthError(f"dynamic client registration failed: {resp.text}")

        data = resp.json()
        new_id = data["client_id"]
        new_secret = data.get("client_secret")
        await creds.store_admin_credentials(
            provider_row["id"],
            {"client_id": new_id, **({"client_secret": new_secret} if new_secret else {})},
        )
        return new_id, new_secret

    # -- authorization request ---------------------------------- #

    async def begin(
        self,
        provider_row: dict[str, Any],
        *,
        user_id: str,
        return_path: str | None,
        include_resource_param: bool,
        client_id: str | None,
        client_secret: str | None,
    ) -> str:
        server_url = provider_row.get("server_url") or provider_row.get("url")
        if not server_url:
            raise MCPAuthError("oauth discovery failed: server has no URL")
        metadata = await self.discover(server_url)
        await self._provider_repo.update(provider_row["id"], oauth_metadata=metadata)

        resolved_id, resolved_secret = await self.ensure_client(
            provider_row, metadata, client_id=client_id, client_secret=client_secret
        )

        await self._session_repo.sweep_expired()

        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(32)
        redirect_uri = self._redirect_uri()

        await self._session_repo.create(
            state=state,
            provider_id=provider_row["id"],
            user_id=user_id,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            return_path=return_path,
            client_id=resolved_id,
            client_secret_encrypted=(encrypt_secret(resolved_secret) if resolved_secret else None),
            token_url=metadata["token_endpoint"],
            resource=metadata["resource"] if include_resource_param else None,
            expires_at=datetime.now(UTC) + timedelta(seconds=env.MCP_OAUTH_SESSION_TTL_SECONDS),
        )

        params = {
            "response_type": "code",
            "client_id": resolved_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if metadata.get("scopes_supported"):
            params["scope"] = " ".join(metadata["scopes_supported"])
        if include_resource_param:
            params["resource"] = metadata["resource"]

        return f"{metadata['authorization_endpoint']}?{urlencode(params)}"

    # -- code exchange ----------------------------------------- #

    async def complete(self, state: str, code: str) -> dict[str, str]:
        session = await self._session_repo.get(state)
        if not session:
            raise MCPAuthError("oauth session not found or expired")

        provider = await self._provider_repo.get_by_id(session["provider_id"]) or {}

        client_secret = (
            decrypt_secret(session["client_secret_encrypted"])
            if session.get("client_secret_encrypted")
            else None
        )
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": session["redirect_uri"],
            "code_verifier": session["code_verifier"],
            "client_id": session["client_id"],
        }
        if client_secret:
            data["client_secret"] = client_secret

        async with httpx.AsyncClient(timeout=env.MCP_OAUTH_HTTP_TIMEOUT) as client:
            resp = await client.post(
                session["token_url"], data=data, headers={"Accept": "application/json"}
            )
        if not resp.is_success:
            raise MCPAuthError(f"oauth token exchange failed: {resp.text}")

        token = resp.json()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=int(token.get("expires_in", env.MCP_OAUTH_DEFAULT_TOKEN_TTL_SECONDS))
        )
        store_user_id = (
            None if provider.get("auth_performer") == MCPAuthPerformer.ADMIN else session["user_id"]
        )

        await MCPCredentialService.get_instance().store_oauth_tokens(
            session["provider_id"],
            store_user_id,
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            expires_at=expires_at,
            scopes=(token.get("scope", "").split() or None),
        )
        await self._provider_repo.set_status(session["provider_id"], MCPServerStatus.CONNECTED)
        await self._session_repo.delete(state)

        return {
            "redirect_url": session.get("return_path") or _DEFAULT_RETURN_PATH,
            "server_name": provider.get("name", ""),
        }
