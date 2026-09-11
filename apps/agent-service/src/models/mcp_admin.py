"""Pydantic models for the Onyx-shaped MCP server admin API.

Request/response shapes mirror the frontend contract in
``apps/web/src/lib/tools/interfaces.ts`` and ``.../mcpService.ts``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from core.mcp_enums import MCPAuthPerformer, MCPAuthType, MCPServerStatus, MCPTransport

_AUTH_TYPES = {e.value for e in MCPAuthType}
_AUTH_PERFORMERS = {e.value for e in MCPAuthPerformer}
_STATUSES = {e.value for e in MCPServerStatus}


def _normalize_transport(value: str | None) -> str:
    return MCPTransport.normalize(value).value


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class MCPServerCreateBody(_Base):
    name: str
    description: str | None = None
    server_url: str


class MCPServerUpdateBody(_Base):
    name: str | None = None
    description: str | None = None
    server_url: str | None = None


class MCPServerUpsertBody(_Base):
    name: str
    description: str | None = None
    server_url: str
    transport: str = "STREAMABLE_HTTP"
    auth_type: str
    auth_performer: str | None = None
    api_token: str | None = None
    auth_template: dict[str, Any] | None = None
    admin_credentials: dict[str, str] | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    existing_server_id: int | None = None

    @field_validator("transport", mode="before")
    @classmethod
    def _transport(cls, v: str | None) -> str:
        return _normalize_transport(v)

    @field_validator("auth_type")
    @classmethod
    def _auth_type(cls, v: str) -> str:
        if v not in _AUTH_TYPES:
            raise ValueError(f"auth_type must be one of {sorted(_AUTH_TYPES)}")
        return v

    @field_validator("auth_performer")
    @classmethod
    def _auth_performer(cls, v: str | None) -> str | None:
        if v is not None and v not in _AUTH_PERFORMERS:
            raise ValueError(f"auth_performer must be one of {sorted(_AUTH_PERFORMERS)}")
        return v


class MCPOAuthConnectBody(_Base):
    server_id: str
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    return_path: str | None = None
    include_resource_param: bool = False


class ToolStatusBody(_Base):
    tool_ids: list[int]
    enabled: bool


class MCPServerStatusQuery(_Base):
    status: str

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in _STATUSES:
            raise ValueError(f"status must be one of {sorted(_STATUSES)}")
        return v


# -- responses --------------------------------------------------------- #


class MCPServerDTO(_Base):
    id: int
    name: str
    description: str = ""
    server_url: str = ""
    owner: str = "system"
    transport: str | None = None
    auth_type: str = "NONE"
    auth_performer: str | None = None
    is_authenticated: bool = False
    user_authenticated: bool = False
    auth_template: dict[str, Any] | None = None
    admin_credentials: dict[str, str] | None = None
    user_credentials: dict[str, str] | None = None
    status: str = "CREATED"
    tool_count: int = 0
    last_refreshed_at: str | None = None


class MCPServersResponse(_Base):
    assistant_id: str | None = None
    mcp_servers: list[MCPServerDTO]


class UpsertMCPServerResponse(_Base):
    server_id: int
    server_name: str
    server_url: str
    auth_type: str
    auth_performer: str | None = None
    is_authenticated: bool


class ToolStatusResponse(_Base):
    updated_count: int
    tool_ids: list[int]


class ToolExecuteBody(_Base):
    arguments: dict[str, Any] = {}


class ToolExecuteResponse(_Base):
    result: Any = None
    error: str | None = None


class OAuthConnectResponse(_Base):
    oauth_url: str


class OAuthCallbackResponse(_Base):
    redirect_url: str
    server_name: str
