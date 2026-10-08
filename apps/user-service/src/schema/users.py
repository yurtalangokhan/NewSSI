from datetime import datetime
from typing import Literal
import uuid

from localization import t
from pydantic import BaseModel, Field, field_validator


class UserCreateRequest(BaseModel):
    email: str
    username: str | None = None
    first_name: str
    last_name: str
    role_id: str | None = Field(default=None, description="Keycloak realm-role ID; defaults to the enduser role.")
    invited: bool = False
    keycloak_id: str | None = None
    password: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError(t("user.names_required"))
        return stripped

    @field_validator("password")
    @classmethod
    def password_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError(t("user.password_required"))
        return stripped


class UserUpdateRequest(BaseModel):
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    team_name: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class UserInviteRequest(BaseModel):
    emails: list[str]


class UserRoleRequest(BaseModel):
    role_id: str = Field(description="Keycloak realm-role ID.")


class UserRolesAssignRequest(BaseModel):
    role_ids: list[str] = Field(min_length=1, description="Keycloak realm-role IDs.")
    primary_role_id: str | None = Field(default=None, description="One of ``role_ids``.")


class RoleCount(BaseModel):
    role: str
    count: int


class RoleDistributionResponse(BaseModel):
    status: Literal["ready", "pending", "unavailable"] = Field(
        description="`pending` while the first snapshot is computed; `unavailable` after a "
        "failed computation with no earlier snapshot."
    )
    distribution: list[RoleCount]
    computed_at: datetime | None = None


class UserActiveRequest(BaseModel):
    is_active: bool


class UserPasswordRequest(BaseModel):
    password: str


class UserChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("old_password", "new_password")
    @classmethod
    def passwords_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError(t("user.password_required"))
        return value


class KeycloakUpsertRequest(BaseModel):
    keycloak_id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class InternalUserBatchRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @field_validator("user_ids")
    @classmethod
    def user_ids_must_be_distinct(cls, user_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(user_ids) != len(set(user_ids)):
            raise ValueError(t("user.ids_must_be_distinct"))
        return user_ids


class InternalUserUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    username: str | None = None


class InternalAuthorizeRequest(BaseModel):
    target_id: str
    permission: str


__all__ = [
    "InternalAuthorizeRequest",
    "InternalUserBatchRequest",
    "InternalUserUpdateRequest",
    "KeycloakUpsertRequest",
    "RoleCount",
    "RoleDistributionResponse",
    "UserActiveRequest",
    "UserChangePasswordRequest",
    "UserCreateRequest",
    "UserInviteRequest",
    "UserPasswordRequest",
    "UserRoleRequest",
    "UserRolesAssignRequest",
    "UserUpdateRequest",
]
