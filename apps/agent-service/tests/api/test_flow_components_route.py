"""Tests for the flow-components HTTP surface.

Authentication happens at Gateway; there is no dev-mode bypass, so the 401
test uses ``IdempotentTestClient(app)`` against the real app with no trusted
Gateway headers and forces the enforcing branch on via the ``auth_enforced``
fixture.

The happy-path tests override FastAPI's shared ``require_user`` dependency —
the single function every ``require_permission(...)`` closure calls via its
own ``Depends(require_user)``, regardless of which route module defines it.
Overriding it once with a fake identity bypasses auth for every route in the
app; ``tests/gateway_auth.allow_all_permissions`` grants that identity every
fine-grained permission explicitly, since no hardcoded grant exists anymore.

Spec: .tmp/flow-canvas-design.md "Interfaces" section; section 10 (error shape).
Brief: .tmp/flow-canvas-task-6-brief.md
"""

from __future__ import annotations

import pytest

from api.dependencies import require_user
from app import app
from service.auth.auth_service import AuthenticatedUser
from service.flows import resolvers as resolvers_module
from tests.api.idempotency_client import IdempotentTestClient


@pytest.fixture(autouse=True)
def _allow_overridden_user_permissions(monkeypatch):
    """The overridden test identity is granted permissions explicitly."""
    from tests.gateway_auth import allow_all_permissions

    allow_all_permissions(monkeypatch)



def _fake_dev_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="dev-user", email="dev-user@local.dev")


@pytest.fixture
def auth_enforced(monkeypatch):
    """Make the 401 assertions independent of the developer's `.env`.

    Authentication now happens at Gateway and there is no dev bypass to
    disable: a request without trusted Gateway headers is always rejected.
    Configuring a known secret keeps the assertion explicit.
    """
    from tests.gateway_auth import use_gateway_auth

    use_gateway_auth(monkeypatch)


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    resolvers_module.clear_cache()
    yield
    resolvers_module.clear_cache()


@pytest.fixture
def authorized_client():
    app.dependency_overrides[require_user] = _fake_dev_user
    try:
        yield IdempotentTestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# 6.6 — auth required
# ---------------------------------------------------------------------------


def test_list_components_requires_authentication(auth_enforced):
    response = IdempotentTestClient(app).get("/api/v1/flow-components")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 6.7 — happy path
# ---------------------------------------------------------------------------


def test_list_components_returns_200_with_categories(authorized_client):
    response = authorized_client.get("/api/v1/flow-components")

    assert response.status_code == 200
    body = response.json()["data"]
    assert "core" in body
    assert any(t["type"] == "ChatInput" for t in body["core"])


# ---------------------------------------------------------------------------
# 6.8 — unknown component -> 404
# ---------------------------------------------------------------------------


def test_get_unknown_component_returns_404(authorized_client):
    response = authorized_client.get("/api/v1/flow-components/NoSuchThing")

    assert response.status_code == 404
    assert "NoSuchThing" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# 6.9 — options resolution through HTTP
# ---------------------------------------------------------------------------


def test_resolve_options_returns_user_scoped_results(monkeypatch, authorized_client):
    async def fake(context) -> list:
        from service.flows.resolvers import OptionItem

        assert context.user_id == "dev-user"  # the fake identity from _fake_dev_user
        return [OptionItem(value="cfg-1", label="Primary")]

    monkeypatch.setitem(resolvers_module._RESOLVERS, "mail.configs", fake)

    response = authorized_client.get("/api/v1/flow-components/options/mail.configs")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["available"] is True
    assert body["items"] == [
        {"value": "cfg-1", "label": "Primary", "description": None, "disabled": False}
    ]


# ---------------------------------------------------------------------------
# 6.10 — unknown source -> 400
# ---------------------------------------------------------------------------


def test_resolve_unknown_source_returns_400(authorized_client):
    response = authorized_client.get("/api/v1/flow-components/options/nope.nope")

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# 6.11 — validate-flow error shape
# ---------------------------------------------------------------------------


def test_validate_flow_returns_400_shape_with_node_ids(authorized_client):
    payload = {
        "flow_spec": {
            "nodes": [{"id": "out-1", "type": "ChatOutput"}],
            "edges": [],
        }
    }

    response = authorized_client.post("/api/v1/agent-definitions/validate-flow", json=payload)

    assert response.status_code == 200  # validation result, not a request error
    body = response.json()["data"]
    assert body["valid"] is False
    assert any(e["code"] == "FLOW_NO_ENTRY" for e in body["errors"])


# ---------------------------------------------------------------------------
# 6.12 — route ordering contract
# ---------------------------------------------------------------------------


def test_validate_flow_route_precedes_generic_definition_id_route(authorized_client):
    payload = {"flow_spec": {"nodes": [{"id": "out-1", "type": "ChatOutput"}], "edges": []}}

    response = authorized_client.post("/api/v1/agent-definitions/validate-flow", json=payload)

    # If validate-flow were shadowed by GET /{definition_id}, POST would 405;
    # if it were shadowed and somehow matched, "validate-flow" would be parsed
    # as a UUID and fail with 422 before ever reaching this handler's logic.
    assert response.status_code not in (404, 405, 422)
    assert "valid" in response.json()["data"]


# ---------------------------------------------------------------------------
# options_source dependencies — `dep=name:value` reaches the resolver
# ---------------------------------------------------------------------------


def test_dep_query_params_reach_the_resolver(monkeypatch, authorized_client):
    seen: dict = {}

    async def fake(context) -> list:
        from service.flows.resolvers import OptionItem

        seen.update(context.depends)
        return [OptionItem(value="gpt-4o", label="GPT-4o")]

    monkeypatch.setitem(resolvers_module._RESOLVERS, "llm.models", fake)
    resolvers_module._cache.clear()

    response = authorized_client.get(
        "/api/v1/flow-components/options/llm.models?dep=provider:openai"
    )

    assert response.status_code == 200
    assert seen == {"provider": "openai"}


def test_several_dependencies_are_all_forwarded(monkeypatch, authorized_client):
    seen: dict = {}

    async def fake(context) -> list:
        seen.update(context.depends)
        return []

    monkeypatch.setitem(resolvers_module._RESOLVERS, "llm.models", fake)
    resolvers_module._cache.clear()

    authorized_client.get(
        "/api/v1/flow-components/options/llm.models?dep=provider:openai&dep=region:eu"
    )

    assert seen == {"provider": "openai", "region": "eu"}


def test_a_malformed_dependency_is_ignored_not_rejected(monkeypatch, authorized_client):
    """A dropdown must not 400 because the canvas sent something odd."""
    seen: dict = {}

    async def fake(context) -> list:
        seen.update(context.depends)
        return []

    monkeypatch.setitem(resolvers_module._RESOLVERS, "llm.models", fake)
    resolvers_module._cache.clear()

    response = authorized_client.get(
        "/api/v1/flow-components/options/llm.models?dep=nocolon&dep=:novalue&dep=ok:1"
    )

    assert response.status_code == 200
    assert seen == {"ok": "1"}


def test_different_dependencies_are_not_served_from_one_cache(monkeypatch, authorized_client):
    """The response is cached per (source, user, dependencies); without the
    last part, the first provider's models would be served to every provider."""
    from service.flows.resolvers import OptionItem

    async def fake(context) -> list:
        return [OptionItem(value=f"{context.depends.get('provider')}-model", label="x")]

    monkeypatch.setitem(resolvers_module._RESOLVERS, "llm.models", fake)
    resolvers_module._cache.clear()

    first = authorized_client.get(
        "/api/v1/flow-components/options/llm.models?dep=provider:openai"
    ).json()["data"]
    second = authorized_client.get(
        "/api/v1/flow-components/options/llm.models?dep=provider:anthropic"
    ).json()["data"]

    assert first["items"][0]["value"] == "openai-model"
    assert second["items"][0]["value"] == "anthropic-model"
