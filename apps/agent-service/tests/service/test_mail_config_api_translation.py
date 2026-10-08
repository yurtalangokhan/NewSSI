from __future__ import annotations

from unittest.mock import AsyncMock

from error_contract import render_error_message
import pytest

from core.exceptions import NotFoundError
from service.auth.mail_config_service import MailConfigService


@pytest.mark.asyncio
class TestMailConfigNotFoundIsTranslated:
    async def test_get_config_not_found_detail_is_translated(self):
        service = AsyncMock()
        service.get_config.return_value = None
        mail_service = MailConfigService(service=service)

        with pytest.raises(NotFoundError) as exc:
            await mail_service.get_config("user-1", "missing-config")

        assert exc.value.status_code == 404
        assert render_error_message(exc.value, locale="tr") == "E-posta yapılandırması bulunamadı."

    async def test_delete_config_not_found_via_value_error_is_translated(self):
        service = AsyncMock()
        service.delete_config.return_value = False
        mail_service = MailConfigService(service=service)

        with pytest.raises(NotFoundError) as exc:
            await mail_service.delete_config("user-1", "missing-config")

        assert exc.value.status_code == 404
        assert render_error_message(exc.value, locale="en") == "Mail configuration not found."

    async def test_test_config_translates_attached_to_agent_error_raised_by_service(self):
        service = AsyncMock()
        service.send_test_email.side_effect = ValueError("Posta yapılandırması bulunamadı")
        mail_service = MailConfigService(service=service)

        with pytest.raises(NotFoundError) as exc:
            await mail_service.test_config("user-1", "config-1", "to@example.com")

        assert exc.value.status_code == 404
        assert render_error_message(exc.value, locale="en") == "Mail configuration not found."


@pytest.mark.asyncio
async def test_list_configs_returns_paginated_structure():
    service = AsyncMock()
    service.list_configs_paginated.return_value = (
        [{"id": "cfg-1", "name": "Work SMTP"}],
        15,
    )
    mail_service = MailConfigService(service=service)

    result = await mail_service.list_configs("user-1", search="work", page=2, page_size=10)

    assert result["items"] == [{"id": "cfg-1", "name": "Work SMTP"}]
    assert result["total_items"] == 15
    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["total_pages"] == 2
    service.list_configs_paginated.assert_awaited_once_with(
        "user-1", search="work", page=2, page_size=10
    )


@pytest.mark.asyncio
async def test_repository_backed_list_configs_returns_paginated_structure():
    repo = AsyncMock()
    repo.list_active.return_value = [
        {
            "id": "cfg-1",
            "name": "Work SMTP",
            "password_encrypted": "encrypted-secret",
        }
    ]
    repo.count_active.return_value = 15
    mail_service = MailConfigService(repo=repo)

    result = await mail_service.list_configs(
        "user-1", search="work", page=2, page_size=10
    )

    assert result == {
        "items": [
            {
                "id": "cfg-1",
                "name": "Work SMTP",
                "password_configured": True,
            }
        ],
        "total_items": 15,
        "page": 2,
        "page_size": 10,
        "total_pages": 2,
    }
    repo.list_active.assert_awaited_once_with(search="work", page=2, page_size=10)
    repo.count_active.assert_awaited_once_with(search="work")
