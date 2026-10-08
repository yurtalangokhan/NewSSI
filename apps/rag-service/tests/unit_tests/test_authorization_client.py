from typing import ClassVar

from src.shared.authorization import AuthorizationClient


class _Response:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {"statusCode": 200, "message": None, "data": {"allowed": True}, "error": None}


class _PooledClient:
    """Stands in for the shared per-peer client (security.get_shared_client).

    The calls used to build their own ``httpx.AsyncClient`` per request; they
    now borrow the pooled one, so the double is a plain object rather than an
    async context manager.
    """

    captured_url: str = ""
    captured_headers: ClassVar[dict[str, str]] = {}

    # **_options absorbs the per-request transport settings (timeout) the
    # caller now passes to the pooled client.
    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, str],
        **_options: object,
    ) -> _Response:
        self.__class__.captured_url = url
        self.__class__.captured_headers = headers
        return _Response()


async def test_authorization_client_uses_api_v1_internal_authorize_path(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.shared.authorization.get_shared_client",
        lambda _name, **_kw: _PooledClient(),
    )
    monkeypatch.setenv(
        "INTERNAL_USER_SERVICE_URL", "http://apisix:8000/internal/user-service"
    )
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "internal-token")

    assert await AuthorizationClient()._fetch_permission_decision(
        user_id="user-1",
        permission="chat:read",
        access_token=None,
    )
    assert (
        _PooledClient.captured_url
        == "http://apisix:8000/internal/user-service/api/v1/internal/users/authorize"
    )
    assert (
        _PooledClient.captured_headers["X-Internal-Service-Token"] == "internal-token"
    )
