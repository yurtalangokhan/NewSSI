"""MCPServerAdmin application use cases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from error_contract import ApplicationError, BadRequestError, NotFoundError, ValidationFailedError

from core.observability.logger import get_logger
from core.security.mcp.mcp_enums import MCPAuthPerformer, MCPAuthType, MCPServerStatus
from schemas.mcp_admin import (
    MCPConnectBody,
    MCPOAuthConnectBody,
    MCPServerCreateBody,
    MCPServerUpdateBody,
    MCPServerUpsertBody,
    MCPServerValidateBody,
    ToolExecuteBody,
    ToolStatusBody,
)
from service.auth.auth_service import AuthenticatedUser
from service.mcp.mcp_admin_helpers import resolve_mcp_provider
from service.mcp.mcp_credential_service import MCPAuthError, MCPCredentialService
from service.mcp.mcp_oauth_service import MCPOAuthService
from service.mcp.mcp_provider_service import MCPProviderService
from service.mcp.mcp_tool_service import MCPToolService

logger = get_logger(__name__)
_VALID_STATUSES = {s.value for s in MCPServerStatus}
_TRANSPORT_STREAMABLE_HTTP = "streamable_http"
_TRANSPORT_SSE = "sse"
# What a provider row holds once nothing is connected to it: the registered state
# the actions-page picker offers. Credentials live in a separate table.
_UNBOUND_CONNECTION: dict[str, Any] = {
    "server_status": MCPServerStatus.CREATED.value,
    "auth_type": MCPAuthType.NONE.value,
    "auth_performer": None,
    "auth_template": None,
    "oauth_metadata": None,
}


class MCPServerAdminApplicationService:
    """Framework-free application use cases for this JSON surface."""

    def __init__(
        self,
        provider_service: Callable[[], MCPProviderService],
        tool_service: Callable[[], MCPToolService],
        oauth_service: Callable[[], MCPOAuthService],
        credential_service: Callable[[], MCPCredentialService],
    ):
        self._provider_service_factory = provider_service
        self._tool_service_factory = tool_service
        self._oauth_service_factory = oauth_service
        self._credential_service_factory = credential_service

    @property
    def provider_service(self) -> MCPProviderService:
        return self._provider_service_factory()

    @property
    def tool_service(self) -> MCPToolService:
        return self._tool_service_factory()

    @property
    def oauth_service(self) -> MCPOAuthService:
        return self._oauth_service_factory()

    @property
    def credential_service(self) -> MCPCredentialService:
        return self._credential_service_factory()

    async def _require_provider(self, server_id: str) -> dict[str, Any]:
        """Resolve a provider by either id the admin API accepts."""
        return await resolve_mcp_provider(self.provider_service, server_id)

    async def _require_external_provider(self, server_id: str) -> dict[str, Any]:
        """Like :meth:`_require_provider`, but the platform's built-in tools are not addressable.

        Connecting or disconnecting the built-in provider would rewrite its auth
        config or wipe its tool cache; it is not a registered catalog entry.
        """
        provider = await self._require_provider(server_id)
        if provider.get("type") == "builtin" or provider.get("is_builtin"):
            raise NotFoundError(message_key="mcp_provider.not_found", message_params={"provider_id": server_id})
        return provider

    async def _drop_connection_data(self, provider_id: str) -> None:
        """Forget everything a connect created for ``provider_id``."""
        await self.credential_service.clear_credentials(provider_id)
        await self.tool_service.delete_tools_by_provider(provider_id)

    async def _bind_credentials(
        self, provider_id: str, body: MCPServerUpsertBody | MCPConnectBody, user: AuthenticatedUser
    ) -> None:
        """Store whichever credential shape ``body`` carries for its auth type."""
        creds = self.credential_service
        if body.auth_type == MCPAuthType.API_TOKEN and body.auth_performer == MCPAuthPerformer.ADMIN and body.api_token:
            await creds.store_admin_credentials(provider_id, {"api_key": body.api_token})
        elif (
            body.auth_type == MCPAuthType.API_TOKEN
            and body.auth_performer == MCPAuthPerformer.PER_USER
            and body.admin_credentials
        ):
            await creds.store_user_credentials(provider_id, user.user_id, body.admin_credentials)
        elif body.auth_type == MCPAuthType.OAUTH and body.oauth_client_id:
            await creds.store_admin_credentials(
                provider_id, {"client_id": body.oauth_client_id, "client_secret": body.oauth_client_secret or ""}
            )

    async def list_mcp_servers(self, user: AuthenticatedUser) -> dict[str, Any]:
        svc = self.provider_service
        rows = await svc.list_external()
        dtos = [await svc.to_mcp_server_dto(r, user_id=user.user_id) for r in rows]
        return {"mcp_servers": [svc.builtin_server_dto(), *dtos]}

    async def get_mcp_server(self, server_id: str, user: AuthenticatedUser) -> dict[str, Any]:
        provider = await self._require_provider(server_id)
        return await self.provider_service.to_mcp_server_dto(provider, user_id=user.user_id, include_credentials=True)

    async def create_mcp_server(self, body: MCPServerCreateBody, user: AuthenticatedUser) -> dict[str, Any]:
        # A URL that does not answer an MCP handshake is not a provider. It is
        # rejected before anything is written, so no half-registered row exists
        # while the probe runs and no compensating delete can fail afterwards.
        #
        # A verified provider stays ``CREATED`` (registered). It becomes a card
        # on /admin/actions/mcp only once an enterprise admin adds it there —
        # registering it on the configuration page is not "adding a server".
        await self._verify_mcp_url(body.server_url, _TRANSPORT_STREAMABLE_HTTP)
        svc = self.provider_service
        provider = await svc.create_provider(
            name=body.name,
            type="external",
            url=body.server_url,
            transport=_TRANSPORT_STREAMABLE_HTTP,
            description=body.description or "",
            auth_type=MCPAuthType.NONE.value,
            server_status=MCPServerStatus.CREATED.value,
            owner_email=user.email,
        )
        return await svc.to_mcp_server_dto(provider, user_id=user.user_id)

    async def validate_mcp_server(self, body: MCPServerValidateBody) -> dict[str, Any]:
        """Probe a URL without persisting; backs the admin "Verify" action."""
        probe = await self.tool_service.probe_endpoint(body.server_url, _TRANSPORT_STREAMABLE_HTTP)
        return {
            "valid": probe.ok or probe.auth_required,
            "auth_required": probe.auth_required,
            "tool_count": len(probe.tools),
        }

    async def update_mcp_server(
        self, server_id: str, body: MCPServerUpdateBody, user: AuthenticatedUser
    ) -> dict[str, Any]:
        provider = await self._require_provider(server_id)
        svc = self.provider_service
        updates: dict[str, Any] = {}
        url_changed = body.server_url is not None and body.server_url != provider.get("url")
        # Re-pointing a provider is re-verified before it is persisted, for the
        # same reason registration is: a non-MCP URL must not enter the catalog.
        if url_changed:
            await self._verify_mcp_url(body.server_url, provider.get("transport") or _TRANSPORT_STREAMABLE_HTTP)
            # Credentials and tools were issued by the old host; replaying them to
            # a new one would hand them to whoever now answers there. The
            # provider goes back to the registered state to be connected afresh.
            if provider.get("server_status") != MCPServerStatus.CREATED.value:
                await self._drop_connection_data(provider["id"])
                updates.update(_UNBOUND_CONNECTION)
        if body.name is not None:
            updates["name"] = body.name
        if body.description is not None:
            updates["description"] = body.description
        if body.server_url is not None:
            updates["url"] = body.server_url
        updated = await svc.update_provider(provider["id"], **updates) if updates else provider
        return await svc.to_mcp_server_dto(updated or provider, user_id=user.user_id)

    async def _verify_mcp_url(self, url: str, transport: str) -> None:
        """Probe ``url`` and raise when it does not answer as an MCP server.

        ``auth_required`` is a valid result: the endpoint is an MCP resource the
        enterprise admin will authenticate once they add it. Verification never
        changes the provider's lifecycle state.
        """
        probe = await self.tool_service.probe_endpoint(url, transport)
        if not probe.ok and not probe.auth_required:
            raise ValidationFailedError(
                message_key="mcp_provider.not_a_mcp_server",
                message_params={"server_url": url},
            )

    async def delete_mcp_server(self, server_id: str) -> dict[str, str]:
        provider = await self._require_provider(server_id)
        await self.tool_service.delete_tools_by_provider(provider["id"])
        await self.provider_service.delete_provider(provider["id"])
        return {"status": "ok"}

    async def set_mcp_server_status(self, server_id: str, status_value: str) -> dict[str, str]:
        if status_value not in _VALID_STATUSES:
            raise ValidationFailedError(
                message_key="mcp_provider.invalid_status", message_params={"status_value": status_value}
            )
        provider = await self._require_provider(server_id)
        await self.provider_service.set_status(provider["id"], status_value)
        return {"status": status_value}

    async def refresh_mcp_server_tools(
        self, server_id: str, user: AuthenticatedUser, source: str = "mcp"
    ) -> list[dict[str, Any]]:
        """``source=mcp`` (default) discovers tools live from the server and upserts
        them; ``source=db`` just returns the cached ``mcp_tool`` rows."""
        provider = await self._require_provider(server_id)
        int_id = provider["int_id"]
        if source == "db":
            return await self.tool_service.list_snapshots_for_provider(int_id)
        try:
            snapshots = await self.tool_service.sync_tools_from_provider(int_id, user_id=user.user_id)
        except ApplicationError:
            await self.provider_service.set_status(provider["id"], MCPServerStatus.DISCONNECTED.value)
            raise
        except (RuntimeError, ValueError) as exc:
            await self.provider_service.set_status(provider["id"], MCPServerStatus.DISCONNECTED.value)
            raise BadRequestError(message_key="common.bad_request") from exc
        await self.provider_service.set_status(provider["id"], MCPServerStatus.CONNECTED.value)
        return snapshots

    async def list_cached_tools(self, server_id: str) -> list[dict[str, Any]]:
        """The tools last synced from a server, read from the database only.

        Unlike ``refresh_mcp_server_tools`` this never contacts the server or
        changes its status, so it needs no more than read access to tools.
        """
        provider = await self._require_provider(server_id)
        return await self.tool_service.list_snapshots_for_provider(provider["int_id"])

    async def execute_mcp_server_tool(
        self, server_id: str, tool_name: str, body: ToolExecuteBody, user: AuthenticatedUser
    ) -> dict[str, Any]:
        provider = await self._require_provider(server_id)
        try:
            return await self.tool_service.execute_tool(
                provider["int_id"], tool_name, body.arguments, user_id=user.user_id
            )
        except ValueError as exc:
            raise NotFoundError(message_key="common.not_found") from exc

    async def upsert_mcp_server(self, body: MCPServerUpsertBody, user: AuthenticatedUser) -> dict[str, Any]:
        svc = self.provider_service
        transport = _TRANSPORT_SSE if body.transport == "SSE" else _TRANSPORT_STREAMABLE_HTTP
        if body.existing_server_id is not None:
            provider = await self._require_provider(str(body.existing_server_id))
        else:
            provider = await svc.create_provider(
                name=body.name,
                type="external",
                url=body.server_url,
                transport=transport,
                description=body.description or "",
                owner_email=user.email,
            )
        provider = (
            await svc.update_provider(
                provider["id"],
                name=body.name,
                url=body.server_url,
                transport=transport,
                auth_type=body.auth_type,
                auth_performer=body.auth_performer,
                auth_template=body.auth_template,
            )
            or provider
        )
        await self._bind_credentials(provider["id"], body, user)
        if body.auth_type == MCPAuthType.OAUTH:
            await svc.set_status(provider["id"], MCPServerStatus.AWAITING_AUTH.value)
        dto = await svc.to_mcp_server_dto(provider, user_id=user.user_id)
        return {
            "server_id": provider["int_id"],
            "server_name": body.name,
            "server_url": body.server_url,
            "auth_type": body.auth_type,
            "auth_performer": body.auth_performer,
            "is_authenticated": dto["is_authenticated"],
        }

    async def connect_mcp_server(self, server_id: str, body: MCPConnectBody, user: AuthenticatedUser) -> dict[str, Any]:
        """Bind credentials to a provider a system admin already registered.

        The provider definition (name/url) is system-admin-owned and is never
        accepted or mutated here: letting this surface carry a url would reopen
        the outbound-request (SSRF) hole the provider/credential split exists to
        close.
        """
        provider = await self._require_external_provider(server_id)
        svc = self.provider_service
        transport = _TRANSPORT_SSE if body.transport == "SSE" else _TRANSPORT_STREAMABLE_HTTP
        updated = await svc.update_provider(
            provider["id"],
            transport=transport,
            auth_type=body.auth_type,
            auth_performer=body.auth_performer,
            auth_template=body.auth_template,
        )
        provider = updated or provider

        await self._bind_credentials(provider["id"], body, user)

        if body.auth_type == MCPAuthType.OAUTH:
            # OAuth still needs the consent round-trip before a tool call can
            # succeed, so stop at "awaiting auth"; the callback flow syncs.
            await svc.set_status(provider["id"], MCPServerStatus.AWAITING_AUTH.value)
        else:
            await self._sync_provider_tools(provider, user_id=user.user_id)

        dto = await svc.to_mcp_server_dto(provider, user_id=user.user_id)
        return {
            "server_id": provider["int_id"],
            "server_name": provider["name"],
            "server_url": provider.get("url") or "",
            "auth_type": body.auth_type,
            "auth_performer": body.auth_performer,
            "is_authenticated": dto["is_authenticated"],
        }

    async def disconnect_mcp_server(self, server_id: str) -> dict[str, str]:
        """Unbind a provider's credentials and return it to the registered catalog.

        The provider definition is system-admin-owned and survives; only what a
        connect created (credentials, discovered tools, auth config, the added
        status) is undone.
        """
        provider = await self._require_external_provider(server_id)
        await self._drop_connection_data(provider["id"])
        await self.provider_service.update_provider(provider["id"], **_UNBOUND_CONNECTION)
        return {"status": "ok"}

    async def _sync_provider_tools(self, provider: dict[str, Any], *, user_id: str) -> None:
        """Discover tools with the freshly-bound credentials and record status.

        Runs inside the connect flow so the callers holding only
        ``mcp_provider:connect`` never need the narrower ``mcp_provider:sync``
        permission just to make the connection usable.
        """
        svc = self.provider_service
        await svc.set_status(provider["id"], MCPServerStatus.FETCHING_TOOLS.value)
        try:
            await self.tool_service.sync_tools_from_provider(provider["int_id"], user_id=user_id)
        except (RuntimeError, ValueError) as exc:
            await svc.set_status(provider["id"], MCPServerStatus.DISCONNECTED.value)
            raise BadRequestError(message_key="common.bad_request") from exc
        await svc.set_status(provider["id"], MCPServerStatus.CONNECTED.value)

    async def mcp_oauth_connect(self, body: MCPOAuthConnectBody, user: AuthenticatedUser) -> dict[str, str]:
        provider = await self._require_provider(str(body.server_id))
        try:
            oauth_url = await self.oauth_service.begin(
                provider,
                user_id=user.user_id,
                return_path=body.return_path,
                include_resource_param=body.include_resource_param,
                client_id=body.oauth_client_id,
                client_secret=body.oauth_client_secret,
            )
        except MCPAuthError as exc:
            raise BadRequestError(message_key="mcp.oauth_failed") from exc
        return {"oauth_url": oauth_url}

    async def set_tool_status(self, body: ToolStatusBody) -> dict[str, Any]:
        updated = await self.tool_service.set_tools_enabled(body.tool_ids, body.enabled)
        return {"updated_count": updated, "tool_ids": body.tool_ids}
