import os
from pathlib import Path

import pytest
from i18n import init_service_i18n
from idempotency import AsyncRedisPool

from langconnect import auth
from langconnect.authorization import AuthorizationClient

init_service_i18n(Path(__file__).resolve().parents[2] / "locales")

if "OPENAI_API_KEY" in os.environ:
    raise AssertionError(
        "Attempting to run unit tests with an OpenAI key in the environment. "
        "Please remove the key from the environment before running tests."
    )

os.environ["OPENAI_API_KEY"] = "test_key"


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> int:
        key = str(keys_and_args[0])
        token = str(keys_and_args[1])
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


@pytest.fixture(autouse=True)
def use_test_auth_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ISSUER_URL", "")

    async def _allow_permission(
        self: AuthorizationClient,
        user_id: str,
        permission: str,
        access_token: str | None = None,
    ) -> bool:
        return True

    monkeypatch.setattr(AuthorizationClient, "has_permission", _allow_permission)

    redis = _FakeRedis()

    async def _connect(config) -> _FakeRedis:
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", _connect)
