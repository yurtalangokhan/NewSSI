"""Role management contracts. Every role is identified by its Keycloak role ID."""

from pydantic import BaseModel, ConfigDict, Field


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompositeRoleCreateRequest(_Request):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    role_ids: list[str] = Field(default_factory=list, description="Keycloak IDs of feature roles to bundle.")


class CompositeRoleUpdateRequest(_Request):
    description: str | None = None
    permissions: list[str] | None = None
    role_ids: list[str] | None = Field(default=None, description="Keycloak IDs of feature roles to bundle.")


class RolePermissionsRequest(_Request):
    permissions: list[str]


class RoleBundlesRequest(_Request):
    role_ids: list[str] = Field(description="Keycloak IDs of feature roles to bundle.")


class CompositeRoleResponse(BaseModel):
    id: str = Field(description="Keycloak realm-role ID.")
    name: str
    description: str | None
    permissions: list[str]
    role_ids: list[str] = Field(description="Keycloak IDs of bundled feature roles.")
    role_names: list[str]
    is_builtin: bool
    is_admin: bool


class CompositeRoleListResponse(BaseModel):
    roles: list[CompositeRoleResponse]


class CompositeRolePermissionsResponse(BaseModel):
    id: str
    name: str
    permissions: list[str] = Field(description="Direct and bundled permissions.")
    role_ids: list[str]
    role_names: list[str]


class CompositeRoleBundlesResponse(BaseModel):
    id: str
    name: str
    role_ids: list[str]
    role_names: list[str]


class CompositeRoleBundlesUpdateResponse(CompositeRoleBundlesResponse):
    effective_permissions: list[str]


class CoarseRoleCreateRequest(_Request):
    name: str = Field(min_length=1, max_length=255)
    service_client: str = Field(min_length=1)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class CoarseRoleUpdateRequest(_Request):
    description: str | None = None


class CoarseRoleResponse(BaseModel):
    id: str = Field(description="Keycloak client-role ID.")
    name: str
    description: str | None
    service_client: str
    permissions: list[str]
    is_builtin: bool


class CoarseRoleListResponse(BaseModel):
    roles: list[CoarseRoleResponse]


class CoarseRolePermissionsResponse(BaseModel):
    id: str
    name: str
    permissions: list[str]


class AggregatedPermissionsResponse(BaseModel):
    permissions: list[str]


class ServiceClientListResponse(BaseModel):
    service_clients: list[str]


class MessageResponse(BaseModel):
    message: str
