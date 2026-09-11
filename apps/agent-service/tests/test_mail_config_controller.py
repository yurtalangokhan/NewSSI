from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from i18n.core import set_locale

from controller.mail_config_controller import MailConfigController


@pytest.mark.asyncio
class TestMailConfigNotFoundIsTranslated:
    async def test_get_config_not_found_detail_is_translated(self):
        service = AsyncMock()
        service.get_config.return_value = None
        controller = MailConfigController(service=service)

        set_locale("tr")
        try:
            with pytest.raises(HTTPException) as exc:
                await controller.get_config("user-1", "missing-config")
        finally:
            set_locale("en")

        assert exc.value.status_code == 404
        assert exc.value.detail == "Posta yapılandırması bulunamadı"

    async def test_delete_config_not_found_via_value_error_is_translated(self):
        service = AsyncMock()
        service.delete_config.return_value = False
        controller = MailConfigController(service=service)

        with pytest.raises(HTTPException) as exc:
            await controller.delete_config("user-1", "missing-config")

        assert exc.value.status_code == 404
        assert exc.value.detail == "Mail config not found"

    async def test_test_config_translates_attached_to_agent_error_raised_by_service(self):
        service = AsyncMock()
        service.send_test_email.side_effect = ValueError("Posta yapılandırması bulunamadı")
        controller = MailConfigController(service=service)

        with pytest.raises(HTTPException) as exc:
            await controller.test_config("user-1", "config-1", "to@example.com")

        assert exc.value.status_code == 404
        assert exc.value.detail == "Posta yapılandırması bulunamadı"


@pytest.mark.asyncio
async def test_list_configs_returns_paginated_structure():
    service = AsyncMock()
    service.list_configs_paginated.return_value = (
        [{"id": "cfg-1", "name": "Work SMTP"}],
        15,
    )
    controller = MailConfigController(service=service)

    result = await controller.list_configs("user-1", search="work", page=2, page_size=10)

    assert result["items"] == [{"id": "cfg-1", "name": "Work SMTP"}]
    assert result["total_items"] == 15
    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["total_pages"] == 2
    service.list_configs_paginated.assert_awaited_once_with(
        "user-1", search="work", page=2, page_size=10
    )
