import uuid
from typing import Any

from src.service import get_api_key_service

from .base import BaseController


class ApiKeyController(BaseController):
    def __init__(self):
        self.service = get_api_key_service()

    async def create_key(self, user_id: uuid.UUID, name: str) -> dict[str, Any]:
        full_key, record = await self.service.create(user_id, name)
        return {**record, "full_key": full_key["full_key"]}

    async def list_keys(self, user_id: uuid.UUID) -> dict[str, Any]:
        keys = await self.service.list_by_user(user_id)
        return {"api_keys": keys}

    async def revoke_key(self, key_id: uuid.UUID) -> dict[str, str]:
        success = await self.service.revoke(key_id)
        if not success:
            self._raise_not_found("API key not found")
        return {"message": "API key revoked"}

    async def delete_key(self, key_id: uuid.UUID) -> dict[str, str]:
        success = await self.service.delete(key_id)
        if not success:
            self._raise_not_found("API key not found")
        return {"message": "API key deleted"}


_api_key_controller: ApiKeyController | None = None


def get_api_key_controller() -> ApiKeyController:
    global _api_key_controller
    if _api_key_controller is None:
        _api_key_controller = ApiKeyController()
    return _api_key_controller
