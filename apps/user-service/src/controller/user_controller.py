import uuid
from typing import Any

from src.core.exceptions import ForbiddenError, NotFoundError
from src.service import get_user_service

from .base import BaseController


class UserController(BaseController):
    def __init__(self):
        self.user_service = get_user_service()

    async def get_me(self, user_id: uuid.UUID) -> dict[str, Any]:
        user = await self.user_service.get_user(user_id)
        if not user:
            self._raise_not_found("User not found")
        return user

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any]:
        user = await self.user_service.get_user(user_id)
        if not user:
            self._raise_not_found("User not found")
        return user

    async def get_user_permissions(self, user_id: uuid.UUID) -> dict[str, list[str]]:
        permissions = await self.user_service.get_user_permissions(user_id)
        if not permissions:
            self._raise_not_found("User not found")
        return permissions

    async def authorize_user_permission(
        self, user_id: uuid.UUID, permission: str
    ) -> dict[str, Any]:
        return await self.user_service.user_has_permission(user_id, permission)

    async def authorize_target_user_id(
        self,
        target_id: str,
        authenticated_user_id: str,
    ) -> uuid.UUID:
        try:
            return await self.user_service.authorize_target_user_id(
                target_id,
                authenticated_user_id,
            )
        except NotFoundError as e:
            self._raise_not_found(str(e))
        except ForbiddenError as e:
            self._raise_forbidden(str(e))

    async def update_me(self, user_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        user = await self.user_service.update_user(user_id, **updates)
        if not user:
            self._raise_not_found("User not found")
        return user

    async def change_password(
        self,
        user_id: uuid.UUID,
        old_password: str,
        new_password: str,
    ) -> dict[str, Any]:
        try:
            user = await self.user_service.change_password(user_id, old_password, new_password)
            if not user:
                self._raise_not_found("User not found")
            return user
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
    ) -> dict[str, Any]:
        users, total = await self.user_service.list_users(
            skip,
            limit,
            query,
            role,
            roles,
            is_active,
            invited,
        )
        return {"users": users, "total": total, "skip": skip, "limit": limit}

    async def create_user(self, **payload: Any) -> dict[str, Any]:
        try:
            return await self.user_service.create_user(**payload)
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def update_user(self, user_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        try:
            user = await self.user_service.update_user(user_id, **updates)
            if not user:
                self._raise_not_found("User not found")
            return user
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def delete_user(self, user_id: uuid.UUID) -> dict[str, str]:
        success = await self.user_service.delete_user(user_id)
        if not success:
            self._raise_not_found("User not found")
        return {"message": "User deleted successfully"}

    async def invite_users(self, emails: list[str]) -> dict[str, Any]:
        users = await self.user_service.invite_users(emails)
        return {"users": users, "count": len(users)}

    async def set_user_role(self, user_id: uuid.UUID, role: str) -> dict[str, Any]:
        try:
            user = await self.user_service.set_user_role(user_id, role)
            if not user:
                self._raise_not_found("User not found")
            return user
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def set_user_active(self, user_id: uuid.UUID, active: bool) -> dict[str, Any]:
        user = await self.user_service.set_user_active(user_id, active)
        if not user:
            self._raise_not_found("User not found")
        return user

    async def reset_password(self, user_id: uuid.UUID) -> dict[str, Any]:
        try:
            password, user = await self.user_service.reset_password(user_id)
            return {"password": password, "user": user}
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def set_password(self, user_id: uuid.UUID, password: str) -> dict[str, Any]:
        try:
            user = await self.user_service.set_password(user_id, password)
            if not user:
                self._raise_not_found("User not found")
            return user
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def download_users_csv(self, query: str | None = None) -> str:
        users, _ = await self.user_service.list_users(0, 10000, query=query)
        import csv
        import io

        output = io.StringIO()
        if users:
            writer = csv.DictWriter(output, fieldnames=users[0].keys())
            writer.writeheader()
            writer.writerows(users)
        return output.getvalue()

    async def upsert_user_from_keycloak(
        self,
        keycloak_id: str,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> dict[str, Any]:
        """Internal method for agent-service to sync users from Keycloak OIDC."""
        try:
            return await self.user_service.upsert_user_from_keycloak(
                keycloak_id=keycloak_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                username=username,
            )
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def get_user_by_keycloak_id(self, keycloak_id: str) -> dict[str, Any]:
        """Fetch user from user-service by Keycloak ID (subject)."""
        user = await self.user_service.get_user_by_keycloak_id(keycloak_id)
        if not user:
            self._raise_not_found(f"User with keycloak_id {keycloak_id} not found")
        return user


_user_controller: UserController | None = None


def get_user_controller() -> UserController:
    global _user_controller
    if _user_controller is None:
        _user_controller = UserController()
    return _user_controller
