"""Admin MCP server routes.

Serves the ``/api/admin/mcp/*`` surface the web admin panel
(``apps/web/src/lib/tools/mcpService.ts``) calls. Storage is the existing
``mcp_provider`` / ``mcp_tool`` tables via :class:`MCPProviderService` and
:class:`MCPToolService` — this router is an adapter that speaks the frontend's
``MCPServer`` shape, not a second store.

Two shape mismatches are handled here:

* the frontend types ``MCPServer.id`` as a ``number`` while providers are keyed
  by UUID — :func:`numeric_id_for` derives a stable 48-bit id from the UUID and
  :func:`_resolve_provider` maps it back (UUIDs are accepted on input too);
* the frontend carries auth/transport/status fields the provider table has no
  columns for — they live under the provider's ``config`` JSONB, with secrets
  encrypted and never echoed back.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from i18n import t

from api.dependencies import require_permission, require_user
from core.logger import get_logger
from service.MCPProviderService import MCPProviderService
from service.MCPToolService import MCPToolService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/mcp",
    tags=["admin-mcp"],
    dependencies=[Depends(require_user)],
)

# Config keys holding secrets: stored encrypted, never returned to the client.
_SECRET_CONFIG_KEYS = ("api_token", "oauth_client_secret", "admin_credentials")

_VALID_STATUSES = {
    "CREATED",
    "AWAITING_AUTH",
    "FETCHING_TOOLS",
    "CONNECTED",
    "DISCONNECTED",
}


def _provider_service() -> MCPProviderService:
    return MCPProviderService.get_instance()


def _tool_service() -> MCPToolService:
    return MCPToolService.get_instance()


def numeric_id_for(provider_id: str) -> int:
    """Derive a stable positive integer id from a provider UUID.

    48 bits keeps the value well inside JavaScript's safe integer range while
    making collisions vanishingly unlikely for realistic provider counts.
    """
    digest = hashlib.blake2b(str(provider_id).encode("utf-8"), digest_size=6).digest()
    return int.from_bytes(digest, "big")


def _server_config(provider: dict[str, Any]) -> dict[str, Any]:
    config = provider.get("config")
    return config if isinstance(config, dict) else {}


def _encrypt(value: str) -> str | None:
    """Encrypt a secret, returning ``None`` when no encryption key is set."""
    try:
        from core.security.encryption import encrypt_secret

        return encrypt_secret(value)
    except Exception as exc:  # pragma: no cover - depends on deployment config
        logger.warning(f"MCP secret not stored — encryption unavailable: {exc}")
        return None


def _store_secrets(config: dict[str, Any], payload: dict[str, Any]) -> None:
    """Move secret fields from ``payload`` into ``config`` in encrypted form."""
    for key in _SECRET_CONFIG_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if value in (None, "", {}):
            config.pop(f"{key}_encrypted", None)
            continue
        raw = value if isinstance(value, str) else json.dumps(value)
        encrypted = _encrypt(raw)
        if encrypted is not None:
            config[f"{key}_encrypted"] = encrypted


def _to_mcp_server(provider: dict[str, Any], tool_count: int = 0) -> dict[str, Any]:
    """Render a provider row in the frontend's ``MCPServer`` shape."""
    config = _server_config(provider)
    auth_type = config.get("auth_type", "NONE")
    is_authenticated = bool(
        auth_type == "NONE" or any(f"{k}_encrypted" in config for k in _SECRET_CONFIG_KEYS)
    )
    return {
        "id": numeric_id_for(provider["id"]),
        "provider_id": provider["id"],
        "name": provider.get("name", ""),
        "description": provider.get("description") or "",
        "server_url": provider.get("url") or "",
        "owner": config.get("owner", "system"),
        "transport": provider.get("transport") or "streamable_http",
        "auth_type": auth_type,
        "auth_performer": config.get("auth_performer", "ADMIN"),
        "is_authenticated": is_authenticated,
        "user_authenticated": is_authenticated,
        "auth_template": config.get("auth_template"),
        "status": config.get("status", "CREATED"),
        "last_refreshed_at": config.get("last_refreshed_at"),
        "tool_count": tool_count,
    }


async def _tool_count(provider_id: str) -> int:
    try:
        tools = await _tool_service().list_tools_by_provider(provider_id)
        return len(tools)
    except Exception as exc:
        logger.warning(f"Failed to count tools for provider {provider_id}: {exc}")
        return 0


async def _resolve_provider(
    server_id: str,
    service: MCPProviderService,
) -> dict[str, Any]:
    """Look a provider up by numeric id (frontend) or UUID (API clients)."""
    if not server_id.isdigit():
        provider = await service.get_provider(server_id)
        if provider is None:
            raise HTTPException(
                status_code=404, detail=t("mcp_provider.not_found", provider_id=server_id)
            )
        return provider

    wanted = int(server_id)
    providers = await service.list_providers(include_inactive=True)
    for provider in providers:
        if numeric_id_for(provider["id"]) == wanted:
            return provider
    raise HTTPException(status_code=404, detail=t("mcp_provider.not_found", provider_id=server_id))


def _to_tool_snapshot(tool: dict[str, Any], server_numeric_id: int) -> dict[str, Any]:
    """Render an ``mcp_tool`` row in the frontend's ``ToolSnapshot`` shape."""
    name = tool.get("name", "")
    return {
        "id": numeric_id_for(tool["id"]),
        "tool_id": tool.get("id"),
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "description": tool.get("description") or "",
        "definition": tool.get("input_schema") or None,
        "custom_headers": [],
        "in_code_tool_id": None,
        "passthrough_auth": False,
        "oauth_config_id": None,
        "oauth_config_name": None,
        "mcp_server_id": server_numeric_id,
        "user_id": None,
        "enabled": bool(tool.get("is_active", True)),
        "chat_selectable": True,
        "agent_creation_selectable": True,
        "default_enabled": bool(tool.get("is_active", True)),
    }


# =============================================================================
# Servers
# =============================================================================


@router.get("/servers")
async def list_mcp_servers(
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:read")),
) -> dict[str, Any]:
    """List configured MCP servers for the admin panel."""
    providers = await service.list_providers(include_inactive=True)
    servers = [_to_mcp_server(p, await _tool_count(p["id"])) for p in providers]
    return {"mcp_servers": servers}


@router.post("/server", status_code=201)
async def create_mcp_server(
    payload: dict[str, Any] = Body(...),
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:create")),
) -> dict[str, Any]:
    """Create an MCP server from the admin panel's "Add server" dialog."""
    name = (payload.get("name") or "").strip()
    server_url = (payload.get("server_url") or payload.get("url") or "").strip()

    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    if not server_url:
        raise HTTPException(status_code=422, detail="server_url is required")

    if await service.get_provider_by_name(name):
        raise HTTPException(
            status_code=409,
            detail=f"An MCP server named '{name}' already exists",
        )

    config: dict[str, Any] = {
        "auth_type": payload.get("auth_type", "NONE"),
        "auth_performer": payload.get("auth_performer", "ADMIN"),
        "status": "CREATED",
    }
    if payload.get("auth_template") is not None:
        config["auth_template"] = payload["auth_template"]
    _store_secrets(config, payload)

    provider = await service.create_provider(
        name=name,
        type="external",
        url=server_url,
        transport=payload.get("transport") or "streamable_http",
        config=config,
        description=payload.get("description") or "",
    )
    return _to_mcp_server(provider)


@router.post("/servers/create")
async def upsert_mcp_server(
    payload: dict[str, Any] = Body(...),
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:create")),
) -> dict[str, Any]:
    """Create or update a server, returning the compact upsert response."""
    name = (payload.get("name") or "").strip()
    server_url = (payload.get("server_url") or payload.get("url") or "").strip()

    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    if not server_url:
        raise HTTPException(status_code=422, detail="server_url is required")

    existing: dict[str, Any] | None = None
    existing_id = payload.get("existing_server_id")
    if existing_id not in (None, ""):
        existing = await _resolve_provider(str(existing_id), service)
    else:
        existing = await service.get_provider_by_name(name)

    config = dict(_server_config(existing)) if existing else {}
    config.update(
        {
            "auth_type": payload.get("auth_type", config.get("auth_type", "NONE")),
            "auth_performer": payload.get("auth_performer", config.get("auth_performer", "ADMIN")),
        }
    )
    if payload.get("auth_template") is not None:
        config["auth_template"] = payload["auth_template"]
    if payload.get("oauth_client_id"):
        config["oauth_client_id"] = payload["oauth_client_id"]
    config.setdefault("status", "CREATED")
    _store_secrets(config, payload)

    if existing:
        provider = await service.update_provider(
            existing["id"],
            name=name,
            url=server_url,
            transport=payload.get("transport") or existing.get("transport"),
            config=config,
            description=payload.get("description") or existing.get("description") or "",
        )
        if provider is None:
            raise HTTPException(
                status_code=404,
                detail=t("mcp_provider.not_found", provider_id=existing["id"]),
            )
    else:
        provider = await service.create_provider(
            name=name,
            type="external",
            url=server_url,
            transport=payload.get("transport") or "streamable_http",
            config=config,
            description=payload.get("description") or "",
        )

    server = _to_mcp_server(provider)
    return {
        "server_id": server["id"],
        "server_name": server["name"],
        "server_url": server["server_url"],
        "auth_type": server["auth_type"],
        "auth_performer": server["auth_performer"],
        "is_authenticated": server["is_authenticated"],
    }


@router.get("/servers/{server_id}")
async def get_mcp_server_alias(
    server_id: str,
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:read")),
) -> dict[str, Any]:
    """Alias for ``GET /server/{id}``.

    The authentication modal fetches the plural spelling; keeping both means a
    frontend typo can never resurface as a 404.
    """
    provider = await _resolve_provider(server_id, service)
    return _to_mcp_server(provider, await _tool_count(provider["id"]))


@router.get("/server/{server_id}")
async def get_mcp_server(
    server_id: str,
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:read")),
) -> dict[str, Any]:
    provider = await _resolve_provider(server_id, service)
    return _to_mcp_server(provider, await _tool_count(provider["id"]))


@router.patch("/server/{server_id}")
async def update_mcp_server(
    server_id: str,
    payload: dict[str, Any] = Body(...),
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:update")),
) -> dict[str, Any]:
    provider = await _resolve_provider(server_id, service)

    updates: dict[str, Any] = {}
    if payload.get("name"):
        updates["name"] = payload["name"].strip()
    if "description" in payload:
        updates["description"] = payload.get("description") or ""
    if payload.get("server_url") or payload.get("url"):
        updates["url"] = (payload.get("server_url") or payload.get("url")).strip()
    if payload.get("transport"):
        updates["transport"] = payload["transport"]

    config = dict(_server_config(provider))
    config_touched = False
    for key in ("auth_type", "auth_performer", "auth_template", "oauth_client_id"):
        if key in payload:
            config[key] = payload[key]
            config_touched = True
    if any(key in payload for key in _SECRET_CONFIG_KEYS):
        _store_secrets(config, payload)
        config_touched = True
    if config_touched:
        updates["config"] = config

    updated = await service.update_provider(provider["id"], **updates)
    if updated is None:
        raise HTTPException(
            status_code=404, detail=t("mcp_provider.not_found", provider_id=server_id)
        )
    return _to_mcp_server(updated, await _tool_count(updated["id"]))


@router.patch("/server/{server_id}/status")
async def update_mcp_server_status(
    server_id: str,
    status: str = Query(...),
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:update")),
) -> dict[str, Any]:
    if status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unsupported status: {status}")

    provider = await _resolve_provider(server_id, service)
    config = dict(_server_config(provider))
    config["status"] = status
    updated = await service.update_provider(
        provider["id"],
        config=config,
        is_active=status != "DISCONNECTED",
    )
    if updated is None:
        raise HTTPException(
            status_code=404, detail=t("mcp_provider.not_found", provider_id=server_id)
        )
    return {"status": status, "server_id": numeric_id_for(provider["id"])}


@router.delete("/server/{server_id}")
async def delete_mcp_server(
    server_id: str,
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_provider:delete")),
) -> dict[str, Any]:
    provider = await _resolve_provider(server_id, service)
    if provider.get("is_builtin"):
        raise HTTPException(status_code=400, detail="The built-in tool service cannot be deleted")
    deleted = await service.delete_provider(provider["id"])
    if not deleted:
        raise HTTPException(
            status_code=404, detail=t("mcp_provider.not_found", provider_id=server_id)
        )
    return {"status": "ok", "server_id": numeric_id_for(provider["id"])}


# =============================================================================
# Tools
# =============================================================================


@router.get("/server/{server_id}/tools/snapshots")
async def get_mcp_server_tool_snapshots(
    server_id: str,
    source: str = Query("db", pattern="^(db|mcp)$"),
    service: MCPProviderService = Depends(_provider_service),
    _user=Depends(require_permission("mcp_tool:read")),
) -> list[dict[str, Any]]:
    """Return this server's tools.

    ``source=db`` reads what is already stored; ``source=mcp`` re-discovers
    tools from the MCP server first, upserts them, then returns the result.
    """
    provider = await _resolve_provider(server_id, service)
    tool_service = _tool_service()

    if source == "mcp":
        config = dict(_server_config(provider))
        try:
            await tool_service.sync_tools_from_provider(provider["id"])
            config["status"] = "CONNECTED"
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning(f"MCP tool refresh failed for {provider['id']}: {exc}")
            config["status"] = "DISCONNECTED"
            await service.update_provider(provider["id"], config=config)
            raise HTTPException(
                status_code=502, detail=f"Failed to reach MCP server: {exc}"
            ) from exc
        config["last_refreshed_at"] = datetime.now(UTC).isoformat()
        await service.update_provider(provider["id"], config=config)

    tools = await tool_service.list_tools_by_provider(provider["id"])
    server_numeric_id = numeric_id_for(provider["id"])
    return [_to_tool_snapshot(tool, server_numeric_id) for tool in tools]


# =============================================================================
# Tool enable/disable
# =============================================================================

tool_router = APIRouter(
    prefix="/api/admin/tool",
    tags=["admin-mcp"],
    dependencies=[Depends(require_user)],
)


@tool_router.patch("/status")
async def update_tool_status(
    payload: dict[str, Any] = Body(...),
    _user=Depends(require_permission("mcp_tool:sync")),
) -> dict[str, Any]:
    """Enable or disable tools by the numeric ids the admin panel holds."""
    tool_ids = payload.get("tool_ids") or []
    if not isinstance(tool_ids, list) or not tool_ids:
        raise HTTPException(status_code=422, detail="tool_ids must be a non-empty list")
    enabled = bool(payload.get("enabled", True))

    tool_service = _tool_service()
    all_tools = await tool_service.list_tools(include_inactive=True)
    by_numeric_id = {numeric_id_for(tool["id"]): tool["id"] for tool in all_tools}

    updated: list[Any] = []
    for raw_id in tool_ids:
        is_numeric = str(raw_id).isdigit()
        uuid_id = by_numeric_id.get(int(raw_id)) if is_numeric else str(raw_id)
        if uuid_id is None:
            continue
        if await tool_service.set_tool_active(uuid_id, enabled):
            updated.append(int(raw_id) if is_numeric else raw_id)

    return {"updated_count": len(updated), "tool_ids": updated}
