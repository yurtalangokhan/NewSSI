from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from i18n.core import set_locale

import api.routes.ThreadsRoute as threads_route
from controller.base import BaseController


class TestBaseControllerTranslatesDetail:
    def test_raise_not_found_translates_key_with_interpolation(self):
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_not_found("agent.not_found", agent_id="my-agent")
        assert exc.value.status_code == 404
        assert exc.value.detail == "Agent my-agent not found"

    def test_raise_not_found_honors_current_locale(self):
        set_locale("tr")
        try:
            controller = BaseController()
            with pytest.raises(HTTPException) as exc:
                controller._raise_not_found("agent.not_found", agent_id="my-agent")
        finally:
            set_locale("en")
        assert exc.value.detail == "my-agent temsilcisi bulunamadı"

    def test_raise_not_found_default_detail_is_translated(self):
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_not_found()
        assert exc.value.detail == "Resource not found"

    def test_raise_bad_request_passes_through_unrecognized_literal_text(self):
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_bad_request("some dynamic validation message")
        assert exc.value.detail == "some dynamic validation message"

    def test_raise_internal_error_default_detail_is_translated(self):
        controller = BaseController()
        with pytest.raises(HTTPException) as exc:
            controller._raise_internal_error()
        assert exc.value.detail == "Internal server error"


@pytest.mark.asyncio
class TestThreadsRouteTranslatesNotFound:
    async def test_get_thread_not_found_uses_translated_detail(self, monkeypatch):
        controller = AsyncMock()
        controller.get_thread.return_value = None
        monkeypatch.setattr(threads_route, "_get_controller", lambda: controller)

        with pytest.raises(HTTPException) as exc:
            await threads_route.get_thread("missing-thread")

        assert exc.value.status_code == 404
        assert exc.value.detail == "Thread not found"

    async def test_delete_thread_not_found_uses_translated_detail(self, monkeypatch):
        controller = AsyncMock()
        controller.delete_thread.return_value = False
        monkeypatch.setattr(threads_route, "_get_controller", lambda: controller)

        with pytest.raises(HTTPException) as exc:
            await threads_route.delete_thread("missing-thread")

        assert exc.value.detail == "Thread not found"
