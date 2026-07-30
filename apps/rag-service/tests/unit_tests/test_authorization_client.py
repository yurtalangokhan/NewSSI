from types import TracebackType
from typing import Self

from langconnect.authorization import AuthorizationClient


class _Response:
    status_code = 200

    def json(self) -> dict[str, bool]:
        return {"allowed": True}


class _AsyncClient:
    captured_url: str = ""

    def __init__(self, timeout: float) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, str],
    ) -> _Response:
        self.__class__.captured_url = url
        return _Response()


async def test_authorization_client_uses_api_v1_internal_authorize_path(
    monkeypatch,
) -> None:
    monkeypatch.setattr("langconnect.authorization.httpx.AsyncClient", _AsyncClient)
    monkeypatch.setattr(
        "langconnect.authorization.config.USER_SERVICE_URL",
        "http://kong:8000/internal/user-service",
    )

    assert await AuthorizationClient()._fetch_permission_decision(
        user_id="user-1",
        permission="chat:read",
        access_token=None,
    )
    assert (
        _AsyncClient.captured_url
        == "http://kong:8000/internal/user-service/api/v1/internal/users/authorize"
    )
