from unittest.mock import AsyncMock

from error_contract import BadRequestError, NotFoundError, render_error_message
import pytest

from src.controller.base import BaseController
from src.controller.role_controller import CompositeRoleController
from src.controller.user_controller import UserController


class TestBaseControllerTranslatesDetail:
    def test_raise_not_found_translates_key_with_interpolation(self):
        controller = BaseController()
        with pytest.raises(NotFoundError) as exc:
            controller._raise_not_found("role.id_not_found", role_id="editor")
        assert exc.value.status_code == 404
        assert render_error_message(exc.value, locale="en") == "Role with ID 'editor' not found"

    def test_raise_not_found_honors_the_requested_locale(self):
        controller = BaseController()
        with pytest.raises(NotFoundError) as exc:
            controller._raise_not_found("role.id_not_found", role_id="editor")
        assert render_error_message(exc.value, locale="tr") == "'editor' ID'li rol bulunamadı"

    def test_raise_not_found_default_detail_is_translated(self):
        controller = BaseController()
        with pytest.raises(NotFoundError) as exc:
            controller._raise_not_found()
        assert render_error_message(exc.value, locale="en") == "Resource not found"

    def test_raise_bad_request_carries_its_catalog_key_and_parameters(self):
        controller = BaseController()
        with pytest.raises(BadRequestError) as exc:
            controller._raise_bad_request("role.invalid_permissions", permissions=["x:y"])
        assert exc.value.status_code == 400
        assert exc.value.message_key == "errors.user_service.role.invalid_permissions"
        assert exc.value.message_params == {"permissions": ["x:y"]}


@pytest.mark.asyncio
class TestControllersRaiseTranslatedErrors:
    async def test_get_role_not_found_includes_role_id_in_detail(self):
        controller = CompositeRoleController()
        controller.service = AsyncMock()
        controller.service.get_role.return_value = None

        with pytest.raises(NotFoundError) as exc:
            await controller.get_role("missing-role-id")

        assert exc.value.status_code == 404
        assert (
            render_error_message(exc.value, locale="en") == "Role with ID 'missing-role-id' not found"
        )

    async def test_get_user_not_found_uses_user_not_found_key(self):
        controller = UserController()
        controller.user_service = AsyncMock()
        controller.user_service.get_user.return_value = None

        with pytest.raises(NotFoundError) as exc:
            await controller.get_user("11111111-1111-1111-1111-111111111111")

        assert render_error_message(exc.value, locale="en") == "User not found"
