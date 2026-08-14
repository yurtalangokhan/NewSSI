"""Mail configuration API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependencies import AuthenticatedUser, require_permission, require_user
from controller.mail_config_controller import get_mail_config_controller
from models.mail_configs import (
    MailConfigCreateRequest,
    MailConfigResponse,
    MailConfigTestRequest,
    MailConfigTestResponse,
    MailConfigUpdateRequest,
    MailSendRequest,
    MailSendResponse,
)

router = APIRouter(
    prefix="/api/mail-configs",
    tags=["mail-configs"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=list[MailConfigResponse])
async def list_mail_configs(
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:read"))],
):
    return await get_mail_config_controller().list_configs(user.user_id)


@router.post("", response_model=MailConfigResponse)
async def create_mail_config(
    body: MailConfigCreateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:create"))],
):
    return await get_mail_config_controller().create_config(user.user_id, body.model_dump())


@router.get("/{config_id}", response_model=MailConfigResponse)
async def get_mail_config(
    config_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:read"))],
):
    return await get_mail_config_controller().get_config(user.user_id, config_id)


@router.patch("/{config_id}", response_model=MailConfigResponse)
async def update_mail_config(
    config_id: str,
    body: MailConfigUpdateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:update"))],
):
    return await get_mail_config_controller().update_config(
        user.user_id,
        config_id,
        body.model_dump(exclude_unset=True),
    )


@router.delete("/{config_id}")
async def delete_mail_config(
    config_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:delete"))],
):
    return await get_mail_config_controller().delete_config(user.user_id, config_id)


@router.post("/{config_id}/test", response_model=MailConfigTestResponse)
async def test_mail_config(
    config_id: str,
    body: MailConfigTestRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:test"))],
):
    return await get_mail_config_controller().test_config(
        user.user_id,
        config_id,
        str(body.to_email),
    )


@router.post("/{config_id}/send", response_model=MailSendResponse)
async def send_mail_with_config(
    config_id: str,
    body: MailSendRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:send"))],
):
    return await get_mail_config_controller().send_email(
        user.user_id,
        config_id,
        body.model_dump(),
    )
