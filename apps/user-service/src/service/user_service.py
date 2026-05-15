import secrets
import uuid
from typing import Any

from src.core.database.models.user_model import UserRole
from src.repository import SessionRepository, UserRepository, UserSettingsRepository

from .auth_service import AuthService
from .keycloak_service import get_keycloak_service

_KEYCLOAK_ROLES = ["admin", "global_curator", "curator", "limited", "basic"]


class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.settings_repo = UserSettingsRepository()
        self.session_repo = SessionRepository()
        self.keycloak = get_keycloak_service()
        self.auth = AuthService()

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        return self._user_to_dict(user)

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_email(email)
        if not user:
            return None
        return self._user_to_dict(user)

    async def get_current_user(self, user_id: str) -> dict[str, Any] | None:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            return None
        user = await self.user_repo.get_by_id(uid)
        if not user:
            return None
        return self._user_to_dict(user)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        users, total = await self.user_repo.list_paginated(skip, limit, query, role, is_active, invited)
        return [self._user_to_dict(u) for u in users], total

    async def get_invited_users(self) -> list[dict[str, Any]]:
        users, _ = await self.user_repo.list_paginated(0, 1000, invited=True)
        return [self._user_to_dict(u) for u in users]

    async def create_user(
        self,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str = "basic",
        password: str | None = None,
        invited: bool = False,
        keycloak_id: str | None = None,
    ) -> dict[str, Any]:
        if await self.user_repo.exists_by_email(email):
            raise ValueError(f"User with email {email} already exists")

        role_enum = UserRole(role) if role in [r.value for r in UserRole] else UserRole.BASIC
        hashed_password = AuthService.hash_password(password) if password else None

        user = await self.user_repo.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role_enum,
            hashed_password=hashed_password,
            invited=invited,
            password_configured=bool(password),
            keycloak_id=keycloak_id,
        )

        await self.settings_repo.ensure_defaults(user.id)

        return self._user_to_dict(user)

    async def invite_users(self, emails: list[str]) -> list[dict[str, Any]]:
        users = []
        for email in emails:
            if await self.user_repo.exists_by_email(email):
                continue
            user = await self.user_repo.create(
                email=email,
                role=UserRole.BASIC,
                invited=True,
                password_configured=False,
            )
            await self.settings_repo.ensure_defaults(user.id)
            users.append(self._user_to_dict(user))
        return users

    async def update_user(self, user_id: uuid.UUID, **updates) -> dict[str, Any] | None:
        allowed = {"first_name", "last_name", "email", "username", "team_name", "is_active", "is_verified"}
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}

        if "role" in updates and updates["role"] in [r.value for r in UserRole]:
            filtered["role"] = UserRole(updates["role"])

        user = await self.user_repo.update(user_id, **filtered)
        if not user:
            return None

        if self.keycloak.is_enabled() and user.keycloak_id:
            payload = {}
            if "first_name" in filtered:
                payload["firstName"] = filtered["first_name"]
            if "last_name" in filtered:
                payload["lastName"] = filtered["last_name"]
            if payload:
                await self.keycloak.update_user(user.keycloak_id, payload)

            if "role" in filtered:
                await self.keycloak.set_realm_role(user.keycloak_id, filtered["role"].value)

        return self._user_to_dict(user)

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False

        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.delete_user(user.keycloak_id)

        return await self.user_repo.delete(user_id)

    async def set_user_active(self, user_id: uuid.UUID, active: bool) -> dict[str, Any] | None:
        user = await self.user_repo.update(user_id, is_active=active)
        if not user:
            return None

        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.update_user(user.keycloak_id, {"enabled": active})

        return self._user_to_dict(user)

    async def set_user_role(self, user_id: uuid.UUID, role: str) -> dict[str, Any] | None:
        if role not in _KEYCLOAK_ROLES:
            raise ValueError(f"Invalid role: {role}")

        role_enum = UserRole(role)
        user = await self.user_repo.update(user_id, role=role_enum)
        if not user:
            return None

        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_realm_role(user.keycloak_id, role)

        return self._user_to_dict(user)

    async def reset_password(self, user_id: uuid.UUID) -> tuple[str, dict[str, Any]]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        new_password = secrets.token_urlsafe(10)
        hashed = AuthService.hash_password(new_password)

        await self.user_repo.update(user_id, hashed_password=hashed, password_configured=True, invited=False)

        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_password(user.keycloak_id, new_password, temporary=False)

        return new_password, self._user_to_dict(await self.user_repo.get_by_id(user_id))

    async def set_password(self, user_id: uuid.UUID, password: str) -> dict[str, Any] | None:
        hashed = AuthService.hash_password(password)
        user = await self.user_repo.update(user_id, hashed_password=hashed, password_configured=True, invited=False)
        if not user:
            return None

        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_password(user.keycloak_id, password, temporary=False)

        return self._user_to_dict(user)

    def _user_to_dict(self, user) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_superuser": user.is_superuser,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "invited": user.invited,
            "password_configured": user.password_configured,
            "team_name": user.team_name,
            "keycloak_id": user.keycloak_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }


_user_service: UserService | None = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
