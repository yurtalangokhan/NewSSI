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
from datetime import UTC, datetime, timedelta
import hashlib
import ipaddress
import secrets
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse

from config_manager import env
import httpx

from core.http import outbound
from core.observability.logger import get_logger
from core.security.encryption import SecretScope, decrypt_secret, encrypt_secret
from core.security.mcp.mcp_enums import MCPAuthPerformer, MCPServerStatus
from infrastructure.db.persistence_gateway import (
    mcp_oauth_session_repository,
    mcp_provider_repository,
)
from service.mcp.mcp_credential_service import MCPAuthError, MCPCredentialService

if TYPE_CHECKING:
    # Type only: the repository itself comes from the gateway at
    # runtime, so the class is never reachable here.
    from infrastructure.db.repositories import (
        MCPOAuthSessionRepository,
        MCPProviderRepository,
    )


__all__ = ["MCPAuthError", "MCPOAuthService"]

logger = get_logger(__name__)

# MCP spec revision advertised on the discovery probe request.
_MCP_PROTOCOL_VERSION = "2025-06-18"
# Path (under MCP_OAUTH_REDIRECT_BASE) the browser is redirected back to.
_OAUTH_CALLBACK_PATH = "/mcp/oauth/callback"
# Where the callback lands the admin when the flow carried no return path.
_DEFAULT_RETURN_PATH = "/admin/actions/mcp"


def _is_loopback(hostname: str | None) -> bool:
    """Whether a redirect to this host never leaves the machine.

    The one case plain http is acceptable for a redirect URI (RFC 8252
    s7.3): nothing observable goes over a network.
    """
    if not hostname:
        return False
    host = hostname.strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class MCPOAuthService:
    """Bootstraps and completes OAuth authorization-code flows for MCP servers."""

    _instance: MCPOAuthService | None = None

    def __init__(
        self,
        provider_repo: MCPProviderRepository | None = None,
        session_repo: MCPOAuthSessionRepository | None = None,
    ) -> None:
        self._provider_repo = provider_repo or mcp_provider_repository()
        self._session_repo = session_repo or mcp_oauth_session_repository()

    @classmethod
    def get_instance(cls) -> MCPOAuthService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- helpers ------------------------------------------------------ #

    @staticmethod
    def _pkce_pair() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)[:128]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return verifier, challenge

    @staticmethod
    def _redirect_uri() -> str:
        """Where the authorization server sends the code back.

        Deliberately has no fallback. With one, a deployment that never
        configured this did not fail -- it asked the remote server to
        deliver authorization codes to whatever was listening on the
        *browser's* own localhost, in cleartext. There is no value that is
        safe to guess here, so an unset base fails the flow instead.
        """
        base = (env.MCP_OAUTH_REDIRECT_BASE or "").strip().rstrip("/")
        if not base:
            raise MCPAuthError(
                "MCP_OAUTH_REDIRECT_BASE is not configured; set it to this "
                "platform's public base URL before starting an MCP OAuth flow."
            )

        parsed = urlparse(base)
        if parsed.scheme != "https" and not _is_loopback(parsed.hostname):
            raise MCPAuthError(
                "MCP_OAUTH_REDIRECT_BASE must use https (plain http is only "
                "allowed for a loopback address): an authorization code sent "
                "in cleartext to a routable host is a leaked credential."
            )

        return f"{base}{_OAUTH_CALLBACK_PATH}"

    # -- discovery -------------------------------------------------- #

    async def discover(self, server_url: str) -> dict[str, Any]:
        parsed = urlparse(server_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.rstrip("/")

        prm = await self._fetch_protected_resource_metadata(origin, path, server_url)
        if not prm or not prm.get("authorization_servers"):
            raise MCPAuthError("oauth discovery failed: no protected-resource metadata")

        as_url = str(prm["authorization_servers"][0]).rstrip("/")
        resource = prm.get("resource") or server_url

        asm = await self._fetch_first_json(
            [
                f"{as_url}/.well-known/oauth-authorization-server",
                f"{as_url}/.well-known/openid-configuration",
            ]
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
        self, origin: str, path: str, server_url: str
    ) -> dict[str, Any] | None:
        candidates = [
            f"{origin}/.well-known/oauth-protected-resource{path}",
            f"{origin}/.well-known/oauth-protected-resource",
        ]
        doc = await self._fetch_first_json(candidates)
        if doc:
            return doc

        # Fallback: probe the MCP endpoint for a WWW-Authenticate hint.
        try:
            probe = await outbound.request(
                outbound.EXTERNAL,
                "GET",
                server_url,
                timeout=env.MCP_OAUTH_HTTP_TIMEOUT,
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
                return await self._fetch_first_json([meta_url])
        return None

    @staticmethod
    async def _fetch_first_json(urls: list[str]) -> dict[str, Any] | None:
        for url in urls:
            try:
                resp = await outbound.request(
                    outbound.EXTERNAL,
                    "GET",
                    url,
                    timeout=env.MCP_OAUTH_HTTP_TIMEOUT,
                    headers={"Accept": "application/json"},
                )
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
            raise MCPAuthError("server requires manual client registration; provide client id/secret")

        body = {
            "client_name": env.MCP_OAUTH_CLIENT_NAME,
            "redirect_uris": [self._redirect_uri()],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        }
        resp = await outbound.request(
            outbound.EXTERNAL,
            "POST",
            registration_endpoint,
            timeout=env.MCP_OAUTH_HTTP_TIMEOUT,
            json=body,
            headers={"Accept": "application/json"},
        )
        if not resp.is_success:
            # The remote body can carry its own error detail and echoed
            # request data; log it, surface only the status.
            logger.warning("Dynamic client registration failed (%s): %s", resp.status_code, resp.text)
            raise MCPAuthError(f"dynamic client registration failed (HTTP {resp.status_code})")

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
            client_secret_encrypted=(
                encrypt_secret(SecretScope.MCP_OAUTH, resolved_secret) if resolved_secret else None
            ),
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

    async def complete(self, state: str, code: str, *, caller_user_id: str | None = None) -> dict[str, str]:
        session = await self._session_repo.get(state)
        if not session:
            raise MCPAuthError("oauth session not found or expired")

        # The resulting tokens are stored against session["user_id"], so the
        # caller finishing the flow must be the user who started it — otherwise
        # a leaked or guessed state lets someone bind their own remote account
        # to another user's MCP server.
        if caller_user_id is not None and str(session.get("user_id")) != str(caller_user_id):
            logger.warning(
                "Rejecting MCP OAuth callback: %s tried to complete a session owned by %s",
                caller_user_id,
                session.get("user_id"),
            )
            raise MCPAuthError("oauth session not found or expired")

        provider = await self._provider_repo.get_by_id(session["provider_id"]) or {}

        client_secret = (
            decrypt_secret(SecretScope.MCP_OAUTH, session["client_secret_encrypted"])
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

        resp = await outbound.request(
            outbound.EXTERNAL,
            "POST",
            session["token_url"],
            timeout=env.MCP_OAUTH_HTTP_TIMEOUT,
            data=data,
            headers={"Accept": "application/json"},
        )
        if not resp.is_success:
            logger.warning("OAuth token exchange failed (%s): %s", resp.status_code, resp.text)
            raise MCPAuthError(f"oauth token exchange failed (HTTP {resp.status_code})")

        token = resp.json()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=int(token.get("expires_in", env.MCP_OAUTH_DEFAULT_TOKEN_TTL_SECONDS))
        )
        store_user_id = None if provider.get("auth_performer") == MCPAuthPerformer.ADMIN else session["user_id"]

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
