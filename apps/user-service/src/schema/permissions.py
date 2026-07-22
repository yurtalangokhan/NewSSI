from pydantic import BaseModel, Field


class PermissionDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = None
    entity: str = Field(min_length=1, max_length=50)
    service: str = Field(min_length=1, max_length=50)
    action: str = Field(min_length=1, max_length=50)
    is_system: bool = False


class PermissionSource(BaseModel):
    service: str
    path: str
    loaded: bool
    count: int = 0
    error: str | None = None


class PermissionSyncResult(BaseModel):
    synced_count: int
    sources: list[PermissionSource]


__all__ = ["PermissionDefinition", "PermissionSource", "PermissionSyncResult"]
