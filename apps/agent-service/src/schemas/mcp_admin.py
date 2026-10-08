"""Pydantic models for the Atlas-shaped MCP server admin API.

Request/response shapes mirror the frontend contract in
``apps/web/src/lib/tools/interfaces.ts`` and ``.../mcpService.ts``.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, RootModel, field_validator

from core.security.mcp.mcp_enums import MCPAuthPerformer, MCPAuthType, MCPServerStatus, MCPTransport
from schemas.base import BaseDomainEntity, BaseSchemaModel

_AUTH_TYPES = {e.value for e in MCPAuthType}
_AUTH_PERFORMERS = {e.value for e in MCPAuthPerformer}
_STATUSES = {e.value for e in MCPServerStatus}


def _normalize_transport(value: str | None) -> str:
    return MCPTransport.normalize(value).value


class _Base(BaseDomainEntity):
    model_config = ConfigDict(extra="ignore")


class MCPServerCreateBody(_Base):
    name: str
    description: str | None = None
    server_url: str


class MCPServerValidateBody(_Base):
    """Probe-only body for the admin "Verify" action (nothing is persisted)."""

    server_url: str


class MCPServerValidateResponse(_Base):
    #: The endpoint answered as an MCP server (whether or not it needs auth).
    valid: bool
    #: The endpoint answered with a 401/403 challenge; credentials are still
    #: needed but it is a real MCP resource.
    auth_required: bool
    #: Tools discovered during a successful handshake.
    tool_count: int


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


class MCPConnectBody(_Base):
    """Auth-only body for binding credentials to an already-registered provider.

    Deliberately has no ``name``/``server_url`` fields: an enterprise admin
    authenticates a provider a system admin registered, and keeping the url out
    of this surface preserves the SSRF boundary the provider/credential split
    exists to draw. ``transport`` is accepted because it is auth-adjacent
    metadata the auth modal already sends.
    """

    transport: str | None = None
    auth_type: str
    auth_performer: str | None = None
    api_token: str | None = None
    auth_template: dict[str, Any] | None = None
    admin_credentials: dict[str, str] | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None

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
    name: str = ""
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
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExecuteResponse(_Base):
    result: Any = None
    error: str | None = None


class OAuthConnectResponse(_Base):
    oauth_url: str


class OAuthCallbackResponse(_Base):
    redirect_url: str
    server_name: str


class MCPProviderResponse(_Base):
    model_config = ConfigDict(extra="allow")
    id: str
    int_id: int | None = None
    name: str
    type: str = "external"
    url: str | None = None
    transport: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    auth_type: str | None = None
    auth_performer: str | None = None
    server_status: str | None = None
    is_active: bool | None = True
    created_at: str | None = None
    updated_at: str | None = None


class MCPToolResponse(_Base):
    model_config = ConfigDict(extra="allow")
    id: str | int
    int_id: int | None = None
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    provider_id: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = True
    enabled: bool | None = True
    created_at: str | None = None
    updated_at: str | None = None


class AvailableToolsResponse(_Base):
    model_config = ConfigDict(extra="allow")
    tools: list[MCPToolResponse]
    categories: list[str]
    total: int


class MCPToolSyncResponse(_Base):
    model_config = ConfigDict(extra="allow")
    provider_id: str
    tools_synced: int


class MCPToolDeleteResponse(_Base):
    model_config = ConfigDict(extra="allow")
    status: str = "ok"
    tool_id: str


class MCPProviderDeleteResponse(_Base):
    model_config = ConfigDict(extra="allow")
    status: str = "ok"
    provider_id: str


class ToolSnapshotResponse(_Base):
    model_config = ConfigDict(extra="allow")
    id: int | str
    name: str
    qualified_name: str | None = None
    display_name: str | None = None
    description: str | None = ""
    definition: Any = None
    custom_headers: list[Any] = Field(default_factory=list)
    in_code_tool_id: str | None = None
    passthrough_auth: bool = False
    oauth_config_id: str | None = None
    oauth_config_name: str | None = None
    mcp_server_id: int | None = None
    user_id: str | None = None
    enabled: bool = True
    chat_selectable: bool = True
    agent_creation_selectable: bool = True
    default_enabled: bool = True
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPToolSyncAllResponse(RootModel[dict[str, int]]):
    """Mapping of provider identifier to number of tools synced."""

    root: dict[str, int]


class MCPProvider(BaseSchemaModel):
    """Schema model representing a Model Context Protocol (MCP) server provider."""

    id: str | None = None
    int_id: int | None = None
    name: str = ""
    type: str = "external"
    url: str | None = None
    transport: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_builtin: bool = False
    description: str | None = None
    auth_type: str = "NONE"
    auth_performer: str | None = None
    server_status: str = "CREATED"
    auth_template: dict[str, Any] | None = None
    owner_email: str | None = None
    oauth_metadata: dict[str, Any] | None = None
    time_created: str | None = None
    time_updated: str | None = None


class MCPTool(BaseSchemaModel):
    """Schema model representing an exposed MCP tool."""

    id: str | None = None
    provider_id: str | None = None
    name: str = ""
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    tool_metadata: dict[str, Any] = Field(default_factory=dict)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    int_id: int | None = None
    enabled: bool = True
    is_active: bool = True
    last_synced: str | None = None
    time_created: str | None = None


# Backward compatibility aliases
MCPProviderEntity = MCPProvider
MCPToolEntity = MCPTool
