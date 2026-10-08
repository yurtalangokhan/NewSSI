"""The acting user comes from the authenticated principal, never the request.

Both the run and agent routes derived `user_id` from the request body or from
a raw `x-api-key` header that nothing validated — and with Keycloak disabled
`extract_user_id_from_token` returns the header's own value as the user id. So
`x-api-key: <someone-else>` (or `{"user_id": "<someone-else>"}`) made the run
act as that person: their long-term memory, their SMTP identity, their thread
ownership. `require_user` already authenticates the API-key path and produces
the principal; these call sites simply ignored it.
"""

from __future__ import annotations

import inspect

import pytest

import api.routes.agents_route as agents_route
import api.routes.run_route as run_route
from schemas.chat import UserInput
from service.auth.auth_service import AuthenticatedUser
from service.orchestration.agent_runner_coordinator import _handle_input

CALLER = AuthenticatedUser(user_id="caller-1", email="caller@example.com")


@pytest.mark.asyncio
async def test_handle_input_uses_the_authenticated_user_over_the_body(monkeypatch):
    captured: dict = {}

    async def fake_thread(*_a, **_k):
        return {"thread_id": "t-1"}

    monkeypatch.setattr("service.runtime.store_service.get_thread_from_store", fake_thread)
    monkeypatch.setattr("service.runtime.store_service.add_thread", fake_thread)

    async def fake_settings(user_id):
        captured["user_id"] = user_id
        return {}

    monkeypatch.setattr("integrations.user_service_client.get_user_settings", fake_settings)

    forged = UserInput(message="hi", thread_id="t-1", user_id="victim-9")

    kwargs, _run_id = await _handle_input(forged, agent=None, authenticated_user_id=CALLER.user_id)

    configurable = kwargs["config"]["configurable"]
    assert configurable["user_id"] == CALLER.user_id
    assert configurable["user_id"] != "victim-9"


def test_the_routes_no_longer_trust_the_x_api_key_header():
    """The header is not an authentication input here — require_user already
    validated (or rejected) it before the handler runs."""
    for module in (run_route, agents_route):
        source = inspect.getsource(module)
        assert "extract_user_id_from_token" not in source, (
            f"{module.__name__} still derives identity from an unvalidated header"
        )
        assert 'headers.get("x-api-key")' not in source


def test_run_route_does_not_read_user_id_from_the_body():
    source = inspect.getsource(run_route)

    assert "request_obj.user_id" not in source
    assert 'body.get("user_id")' not in source
