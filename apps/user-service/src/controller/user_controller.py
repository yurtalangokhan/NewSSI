import uuid
from typing import Any

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

    async def update_me(self, user_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        user = await self.user_service.update_user(user_id, **updates)
        if not user:
            self._raise_not_found("User not found")
        return user

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
    ) -> dict[str, Any]:
        users, total = await self.user_service.list_users(skip, limit, query, role, is_active, invited)
        return {"users": users, "total": total, "skip": skip, "limit": limit}

    async def create_user(self, **payload: Any) -> dict[str, Any]:
        try:
            return await self.user_service.create_user(**payload)
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def update_user(self, user_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        user = await self.user_service.update_user(user_id, **updates)
        if not user:
            self._raise_not_found("User not found")
        return user

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
        user = await self.user_service.set_password(user_id, password)
        if not user:
            self._raise_not_found("User not found")
        return user

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


_user_controller: UserController | None = None


def get_user_controller() -> UserController:
    global _user_controller
    if _user_controller is None:
        _user_controller = UserController()
    return _user_controller
