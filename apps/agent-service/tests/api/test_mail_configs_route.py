"""Tests for the mail configs list use case behind GET /api/mail-configs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from error_contract import ConfigurationError, NotFoundError
from fastapi import Request, Response
import pytest

from api.routes.mail_configs_route import (
    test_user_mail_credentials as run_user_mail_test,
    upsert_user_mail_credentials,
)
from schemas.mail_configs import UserMailSettingsRequest, UserMailSettingsTestRequest
from service.auth.mail_configs_application_service import list_mail_configs


@pytest.mark.asyncio
async def test_list_mail_configs_returns_paginated_shape():
    """GET /api/mail-configs declares ResponseModel[PaginatedMailConfigsResponse],
    so the use case must return that dict shape, not the flat list that
    MailConfigService.list_configs returns in production (no injected service)."""
    service = AsyncMock()
    service.list_configs_paginated.return_value = (
        [{"id": "config-1", "name": "Work SMTP"}],
        1,
    )

    with patch("service.auth.mail_configs_application_service.get_mail_config_service", return_value=service):
        result = await list_mail_configs(user_id="user-1", search=None, page=1, page_size=10)

    assert result == {
        "items": [{"id": "config-1", "name": "Work SMTP"}],
        "total_items": 1,
        "page": 1,
        "page_size": 10,
        "total_pages": 1,
    }
    service.list_configs_paginated.assert_awaited_once_with(
        "user-1", search=None, page=1, page_size=10
    )


@pytest.mark.asyncio
async def test_user_mail_save_reports_invalid_selection_in_error_envelope():
    service = AsyncMock()
    service.upsert_user_credentials.side_effect = NotFoundError(code="mail.config_unavailable", message_key="errors.mail.config_unavailable")
    sample_value = "secret"
    body = UserMailSettingsRequest(
        mail_config_id="missing",
        username="sender@example.com",
        password=sample_value,
        from_email="sender@example.com",
    )

    request = Request({"type": "http", "headers": [], "query_string": b""})
    response = Response()
    with patch("service.auth.mail_configs_application_service.get_mail_config_service", return_value=service):
        result = await upsert_user_mail_credentials(
            request=request, response=response, body=body, user=SimpleNamespace(user_id="user-1")
        )
    assert response.status_code == 404
    assert result.statusCode == 404
    assert result.data is None
    assert result.error.code == "mail.config_unavailable"
    service.upsert_user_credentials.assert_awaited_once_with("user-1", body.model_dump())


@pytest.mark.asyncio
async def test_user_mail_test_reports_unsaved_credentials_in_error_envelope():
    service = AsyncMock()
    service.test_user_credentials.side_effect = ConfigurationError(code="mail.credentials_required", message_key="errors.mail.credentials_required")
    body = UserMailSettingsTestRequest(mail_config_id="config-1")

    request = Request({"type": "http", "headers": [], "query_string": b""})
    response = Response()
    with patch("service.auth.mail_configs_application_service.get_mail_config_service", return_value=service):
        result = await run_user_mail_test(
            request=request, response=response, body=body, user=SimpleNamespace(user_id="user-1")
        )
    assert response.status_code == ConfigurationError.status_code
    assert result.statusCode == response.status_code
    assert result.data is None
    assert result.error.code == "mail.credentials_required"
    service.test_user_credentials.assert_awaited_once_with("user-1", "config-1", None)
