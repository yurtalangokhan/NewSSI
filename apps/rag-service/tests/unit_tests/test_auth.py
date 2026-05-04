from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from langconnect import auth


def _request(headers: dict[str, str] | None = None, host: str = "127.0.0.1"):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=host))


def _credentials(token: str):
    return SimpleNamespace(scheme="Bearer", credentials=token)


@pytest.fixture(autouse=True)
def clear_auth_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "VALID_API_KEYS", set())


def test_verify_api_key_uses_bearer_identity_in_test_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    assert auth.verify_api_key("user1") == "user1"
    assert auth.verify_api_key("api-key:user2") == "user2"


def test_resolve_user_requires_credentials_in_test_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    with pytest.raises(HTTPException) as exc:
        auth.resolve_user(_request(), None)

    assert exc.value.status_code == 403


def test_resolve_user_does_not_trust_localhost_without_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "IS_TESTING", False)
    monkeypatch.setattr(auth, "ALLOW_LOCAL_INTERNAL_BYPASS", False)
    monkeypatch.setattr(auth, "VALID_API_KEYS", {"expected-key"})

    with pytest.raises(HTTPException) as exc:
        auth.resolve_user(
            _request(headers={"User-Agent": "python-httpx/0.28.1"}),
            None,
        )

    assert exc.value.status_code == 403


def test_resolve_user_accepts_internal_service_token():
    user = auth.resolve_user(
        _request(headers={"X-Internal-Service-Token": auth.INTERNAL_SERVICE_TOKEN}),
        None,
    )
    assert user is not None
    assert user.identity == "internal-service"


def test_resolve_user_uses_bearer_identity_in_test_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    user = auth.resolve_user(_request(), _credentials("user-123"))
    assert user is not None
    assert user.identity == "user-123"