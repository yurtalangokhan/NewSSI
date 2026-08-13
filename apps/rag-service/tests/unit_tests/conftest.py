import asyncio
import os
from pathlib import Path

import pytest
from i18n import init_service_i18n

from langconnect import auth
from langconnect.authorization import AuthorizationClient

init_service_i18n(Path(__file__).resolve().parents[2] / "locales")

if "OPENAI_API_KEY" in os.environ:
    raise AssertionError(
        "Attempting to run unit tests with an OpenAI key in the environment. "
        "Please remove the key from the environment before running tests."
    )

os.environ["OPENAI_API_KEY"] = "test_key"


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


@pytest.fixture(scope="session")
def event_loop():
    """Create a single asyncio event loop for the entire test session,
    and only close it once at the very end.
    This overrides pytest-asyncio's default event_loop fixture.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
