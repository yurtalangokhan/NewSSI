from pydantic import BaseModel, Field

from models.auth import DEFAULT_PREFERENCES


class User(BaseModel):
    id: str = "dev-user-1"
    email: str = "dev@local.dev"
    is_active: bool = True
    is_verified: bool = True
    role: str = "enduser"
    preferences: dict = Field(default_factory=lambda: DEFAULT_PREFERENCES.copy())
    team_name: str | None = None
    is_anonymous_user: bool = False
    password_configured: bool = True


class Settings(BaseModel):
    auto_scroll: bool = True
    application_status: str = "active"
    gpu_enabled: bool = False
    maximum_chat_retention_days: str | None = None
    notifications: list = Field(default_factory=list)
    needs_reindexing: bool = False
    anonymous_user_enabled: bool = True
    invite_only_enabled: bool = False
    deep_research_enabled: bool = True
    temperature_override_enabled: bool = True
    query_history_type: str = "normal"
