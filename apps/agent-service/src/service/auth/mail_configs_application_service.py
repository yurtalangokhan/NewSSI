from __future__ import annotations

from schemas.common import SuccessResponse
from schemas.mail_configs import (
    AvailableMailConfigResponse,
    MailConfigCreateRequest,
    MailConfigResponse,
    MailConfigTestRequest,
    MailConfigTestResponse,
    MailConfigUpdateRequest,
    MailSendRequest,
    MailSendResponse,
    PaginatedMailConfigsResponse,
    UserMailSettingsRequest,
    UserMailSettingsResponse,
    UserMailSettingsTestRequest,
)
from service.auth.mail_config_service import get_mail_config_service


async def list_available_mail_configs(user_id: str) -> list[AvailableMailConfigResponse]:
    return await get_mail_config_service().list_available_configs(user_id)


async def get_user_mail_credentials(user_id: str) -> UserMailSettingsResponse | None:
    return await get_mail_config_service().get_user_credentials(user_id)


async def upsert_user_mail_credentials(user_id: str, body: UserMailSettingsRequest) -> UserMailSettingsResponse:
    return await get_mail_config_service().upsert_user_credentials(user_id, body.model_dump())


async def delete_user_mail_credentials(user_id: str) -> SuccessResponse:
    return await get_mail_config_service().delete_user_credentials(user_id)


async def test_user_mail_credentials(user_id: str, body: UserMailSettingsTestRequest) -> MailConfigTestResponse:
    return await get_mail_config_service().test_user_credentials(user_id, body.mail_config_id, body.to_email)


async def list_mail_configs(
    user_id: str, search: str | None, page: int, page_size: int
) -> PaginatedMailConfigsResponse:
    items, total = await get_mail_config_service().list_configs_paginated(
        user_id, search=search, page=page, page_size=page_size
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
    return {"items": items, "total_items": total, "page": page, "page_size": page_size, "total_pages": total_pages}


async def create_mail_config(user_id: str, body: MailConfigCreateRequest) -> MailConfigResponse:
    return await get_mail_config_service().create_config(user_id, body.model_dump())


async def get_mail_config(user_id: str, config_id: str) -> MailConfigResponse:
    return await get_mail_config_service().get_config(user_id, config_id)


async def update_mail_config(user_id: str, config_id: str, body: MailConfigUpdateRequest) -> MailConfigResponse:
    return await get_mail_config_service().update_config(user_id, config_id, body.model_dump(exclude_unset=True))


async def delete_mail_config(user_id: str, config_id: str) -> SuccessResponse:
    return await get_mail_config_service().delete_config(user_id, config_id)


async def test_mail_config(user_id: str, config_id: str, body: MailConfigTestRequest) -> MailConfigTestResponse:
    return await get_mail_config_service().test_config(user_id, config_id, str(body.to_email))


async def send_mail_with_config(user_id: str, config_id: str, body: MailSendRequest) -> MailSendResponse:
    return await get_mail_config_service().send_email(user_id, config_id, body.model_dump())
