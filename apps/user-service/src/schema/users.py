import uuid

from pydantic import BaseModel, Field, field_validator


class UserCreateRequest(BaseModel):
    email: str
    username: str | None = None
    first_name: str
    last_name: str
    role: str = "enduser"
    invited: bool = False
    keycloak_id: str | None = None
    password: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("first_name and last_name are required")
        return stripped

    @field_validator("password")
    @classmethod
    def password_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Password is required")
        return stripped


class UserUpdateRequest(BaseModel):
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    team_name: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    role: str | None = None


class UserInviteRequest(BaseModel):
    emails: list[str]


class UserRoleRequest(BaseModel):
    role: str


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
            raise ValueError("Password is required")
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
            raise ValueError("user_ids must be distinct")
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
    "UserActiveRequest",
    "UserChangePasswordRequest",
    "UserCreateRequest",
    "UserInviteRequest",
    "UserPasswordRequest",
    "UserRoleRequest",
    "UserUpdateRequest",
]
