import os
from pathlib import Path

import pytest
from idempotency import AsyncRedisPool
from localization import init_localization

from src.shared import auth
from src.shared.authorization import AuthorizationClient

init_localization(Path(__file__).resolve().parents[2] / "locales")

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

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if self.values.pop(key, None) is not None:
                deleted += 1
        return deleted


@pytest.fixture(autouse=True)
def use_test_auth_mode(monkeypatch: pytest.MonkeyPatch):
    from tests.unit_tests.fixtures import GATEWAY_SECRET

    monkeypatch.setenv("IS_TESTING", "true")
    # rag-service authenticates only from the trusted headers Gateway sets, so
    # the suite configures the service with the secret those headers carry.
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", GATEWAY_SECRET)
    monkeypatch.setenv(
        "INTERNAL_USER_SERVICE_URL", "http://apisix:8000/internal/user-service"
    )

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
