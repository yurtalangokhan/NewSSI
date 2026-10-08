from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request, Response
from localization.core import set_locale

import api.routes.threads_route as threads_route
from core.exceptions import (
    ApplicationError,
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
)
from service.auth.auth_service import AuthenticatedUser
from service.common.base import BaseService

_USER = AuthenticatedUser(user_id="user-1", email="user@example.com")


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})


class TestBaseServiceTranslatesMessage:
    """The helpers raise transport-free domain errors carrying a translated message."""

    def test_raise_not_found_translates_key_with_interpolation(self):
        service = BaseService()
        with pytest.raises(NotFoundError) as exc:
            service._raise_not_found("agent.not_found", agent_id="my-agent")
        assert exc.value.status_code == 404
        assert exc.value.code == "request.not_found"
        assert exc.value.message == "Agent my-agent not found"

    def test_raise_not_found_honors_current_locale(self):
        set_locale("tr")
        try:
            service = BaseService()
            with pytest.raises(NotFoundError) as exc:
                service._raise_not_found("agent.not_found", agent_id="my-agent")
        finally:
            set_locale("en")
        assert exc.value.message == "my-agent temsilcisi bulunamadı"

    def test_raise_not_found_default_detail_is_translated(self):
        service = BaseService()
        with pytest.raises(NotFoundError) as exc:
            service._raise_not_found()
        assert exc.value.message == "Resource not found"

    def test_raise_bad_request_passes_through_unrecognized_literal_text(self):
        service = BaseService()
        with pytest.raises(BadRequestError) as exc:
            service._raise_bad_request("some dynamic validation message")
        assert exc.value.status_code == 400
        assert exc.value.message == "some dynamic validation message"

    def test_raise_unauthorized_carries_the_contract_status_and_code(self):
        service = BaseService()
        with pytest.raises(UnauthorizedError) as exc:
            service._raise_unauthorized()
        assert exc.value.status_code == 401
        assert exc.value.code == "auth.unauthorized"

    def test_raise_internal_error_does_not_echo_the_detail_to_the_caller(self):
        """A 5xx body must not leak internals; the detail belongs in the log."""
        service = BaseService()
        with pytest.raises(ApplicationError) as exc:
            service._raise_internal_error("psycopg: connection string rejected")
        assert exc.value.status_code == 500
        assert exc.value.code == "internal.server_error"
        assert "psycopg" not in exc.value.message


class TestBaseServiceErrorsAreTransportFree:
    def test_domain_errors_are_not_http_exceptions(self):
        """Nothing below the route layer may raise a FastAPI/Starlette error."""
        service = BaseService()
        with pytest.raises(NotFoundError) as exc:
            service._raise_not_found()
        assert not isinstance(exc.value, HTTPException)


@pytest.mark.asyncio
class TestThreadsRouteTranslatesNotFound:
    async def test_get_thread_not_found_uses_translated_detail(self, monkeypatch):
        service = AsyncMock()
        service.get_thread.return_value = None
        monkeypatch.setattr(threads_route, "_get_service", lambda: service)
        monkeypatch.setattr("api.thread_access.get_thread_access_service", lambda: service, raising=False)

        response = Response()
        result = await threads_route.get_thread(response, "missing-thread", user=_USER, request=_request())

        assert response.status_code == 404
        assert result.error.message == "Thread not found"

    async def test_delete_thread_not_found_uses_translated_detail(self, monkeypatch):
        service = AsyncMock()
        service.delete_thread.return_value = False
        monkeypatch.setattr(threads_route, "_get_service", lambda: service)
        monkeypatch.setattr("api.thread_access.get_thread_access_service", lambda: service, raising=False)

        result = await threads_route.delete_thread(Response(), "missing-thread", user=_USER, request=_request())

        assert result.error.message == "Thread not found"
