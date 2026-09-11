"""Controller for SMTP mail config endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from i18n import t

from controller.base import BaseController
from service.MailConfigService import MailConfigService, get_mail_config_service


class MailConfigController(BaseController):
    """Translate mail config service outcomes to HTTP responses."""

    def __init__(self, service: MailConfigService | None = None):
        self.service = service or get_mail_config_service()

    async def list_configs(
        self,
        user_id: str,
        search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        items, total = await self.service.list_configs_paginated(
            user_id, search=search, page=page, page_size=page_size
        )
        total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
        return {
            "items": items,
            "total_items": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def list_available_configs(self, user_id: str) -> list[dict[str, Any]]:
        return await self.service.list_available_configs(user_id)

    async def create_config(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.service.create_config(user_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def get_config(self, user_id: str, config_id: str) -> dict[str, Any]:
        config = await self.service.get_config(user_id, config_id)
        if not config:
            raise HTTPException(status_code=404, detail=t("mailConfig.notFound"))
        return config

    async def update_config(
        self,
        user_id: str,
        config_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            config = await self.service.update_config(user_id, config_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not config:
            raise HTTPException(status_code=404, detail=t("mailConfig.notFound"))
        return config

    async def delete_config(self, user_id: str, config_id: str) -> dict[str, bool]:
        try:
            deleted = await self.service.delete_config(user_id, config_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail=t("mailConfig.notFound"))
        return {"success": True}

    async def test_config(
        self,
        user_id: str,
        config_id: str,
        to_email: str,
    ) -> dict[str, Any]:
        try:
            return await self.service.send_test_email(user_id, config_id, to_email)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def send_email(
        self,
        user_id: str,
        config_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await self.service.send_email(user_id, config_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -------------------------------------------------------------------------
    # User-specific credentials controller methods
    # -------------------------------------------------------------------------

    async def get_user_credentials(self, user_id: str) -> dict[str, Any] | None:
        return await self.service.get_user_credentials(user_id)

    async def upsert_user_credentials(
        self,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await self.service.upsert_user_credentials(user_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def delete_user_credentials(self, user_id: str) -> dict[str, bool]:
        await self.service.delete_user_credentials(user_id)
        return {"success": True}

    async def test_user_credentials(
        self,
        user_id: str,
        mail_config_id: str,
        to_email: str | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.service.test_user_credentials(
                user_id,
                mail_config_id,
                to_email,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


_mail_config_controller: MailConfigController | None = None


def get_mail_config_controller() -> MailConfigController:
    global _mail_config_controller
    if _mail_config_controller is None:
        _mail_config_controller = MailConfigController()
    return _mail_config_controller
