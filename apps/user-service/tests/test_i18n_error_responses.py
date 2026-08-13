from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from i18n.core import set_locale

from src.controller.base import BaseController
from src.controller.role_controller import CompositeRoleController
from src.controller.user_controller import UserController


class TestBaseControllerTranslatesDetail:
    def test_raise_not_found_translates_key_with_interpolation(self):
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_not_found("role.not_found", name="editor")
        assert exc.value.status_code == 404
        assert exc.value.detail == "Role 'editor' not found"

    def test_raise_not_found_honors_current_locale(self):
        set_locale("tr")
        try:
            controller = BaseController()
            with pytest.raises(HTTPException) as exc:
                controller._raise_not_found("role.not_found", name="editor")
        finally:
            set_locale("en")
        assert exc.value.detail == "'editor' rolü bulunamadı"

    def test_raise_not_found_default_detail_is_translated(self):
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_not_found()
        assert exc.value.detail == "Resource not found"

    def test_raise_bad_request_passes_through_unrecognized_literal_text(self):
        # Dynamic exception text (e.g. str(exc)) has no matching key, so it
        # is returned unchanged rather than mistranslated.
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_bad_request("some dynamic validation message")
        assert exc.value.detail == "some dynamic validation message"


@pytest.mark.asyncio
class TestControllersRaiseTranslatedErrors:
    async def test_get_role_not_found_includes_role_name_in_detail(self):
        controller = CompositeRoleController()
        controller.service = AsyncMock()
        controller.service.get_role.return_value = None

        with pytest.raises(HTTPException) as exc:
            await controller.get_role("missing-role")

        assert exc.value.status_code == 404
        assert exc.value.detail == "Role 'missing-role' not found"

    async def test_get_user_not_found_uses_user_not_found_key(self):
        controller = UserController()
        controller.user_service = AsyncMock()
        controller.user_service.get_user.return_value = None

        with pytest.raises(HTTPException) as exc:
            await controller.get_user("11111111-1111-1111-1111-111111111111")

        assert exc.value.detail == "User not found"
