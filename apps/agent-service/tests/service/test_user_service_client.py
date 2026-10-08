import pytest
from security.resilience import CircuitBreakerOpenError

from core.exceptions import DependencyUnavailableError
from integrations import user_service_client as UserServiceClient


@pytest.mark.asyncio
async def test_open_circuit_is_a_typed_dependency_error(monkeypatch) -> None:
    from core.http import outbound

    class OpenCircuit:
        async def __aenter__(self):
            raise CircuitBreakerOpenError("user-service", 6.4)

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(outbound, "get_circuit_breaker", lambda _: OpenCircuit())
    monkeypatch.setattr(UserServiceClient, "_user_service_base_url", lambda: "http://users")

    def fail_transport(_dependency):
        raise AssertionError("An open circuit must not issue an HTTP request")

    monkeypatch.setattr(outbound, "get_client", fail_transport)
    with pytest.raises(DependencyUnavailableError) as raised:
        await UserServiceClient._request("GET", "/api/v1/internal/users/user-1/settings")

    assert raised.value.status_code == 503
    assert raised.value.code == "user-service.circuit_open"
    assert raised.value.details == {"reset_in_seconds": 6.4}
    assert raised.value.headers["Retry-After"] == "6"


@pytest.mark.asyncio
async def test_get_user_by_keycloak_id_skips_dev_placeholder(monkeypatch) -> None:
    async def fail_request(*args, **kwargs):
        raise AssertionError("dev placeholder should not call user-service")

    UserServiceClient._USER_BY_KEYCLOAK_ID_CACHE.clear()
    monkeypatch.setattr(UserServiceClient, "_request", fail_request)

    assert await UserServiceClient.get_user_by_keycloak_id("user-1") is None


@pytest.mark.asyncio
async def test_get_user_by_keycloak_id_caches_lookup(monkeypatch) -> None:
    calls = 0

    async def fake_request(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"id": "local-user-id"}

    UserServiceClient._USER_BY_KEYCLOAK_ID_CACHE.clear()
    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    keycloak_id = "11111111-1111-4111-8111-111111111111"

    assert await UserServiceClient.get_user_by_keycloak_id(keycloak_id) == {"id": "local-user-id"}
    assert await UserServiceClient.get_user_by_keycloak_id(keycloak_id) == {"id": "local-user-id"}
    assert calls == 1


@pytest.mark.asyncio
async def test_user_service_client_uses_api_v1_internal_permission_path(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"permissions": ["chat:read"]}

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    assert await UserServiceClient.get_user_permissions("user-1") == {"permissions": ["chat:read"]}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/internal/users/user-1/permissions"
    assert captured["kwargs"]["include_internal_token"] is True


@pytest.mark.asyncio
async def test_create_audit_log_uses_api_v1_internal_audit_logs_path(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"id": "log-1"}

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    result = await UserServiceClient.create_audit_log(
        "flow:published",
        "flow:abc123",
        user_id="real-uuid",
        details={"to_version": 2},
        access_token="tok",
    )

    assert result == {"id": "log-1"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/internal/audit-logs"
    assert captured["kwargs"] == {
        "json_body": {
            "action": "flow:published",
            "resource": "flow:abc123",
            "user_id": "real-uuid",
            "details": {"to_version": 2},
        },
        "access_token": "tok",
        "include_internal_token": True,
    }


@pytest.mark.asyncio
async def test_user_service_client_uses_api_v1_internal_keycloak_upsert_path(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"id": "local-user-id"}

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    assert await UserServiceClient.upsert_user_from_keycloak(
        keycloak_id="keycloak-id",
        email="user@example.com",
    ) == {"id": "local-user-id"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/internal/users/upsert-from-keycloak"
    assert captured["kwargs"] == {
        "json_body": {
            "keycloak_id": "keycloak-id",
            "email": "user@example.com",
            "first_name": None,
            "last_name": None,
            "username": None,
        },
        "access_token": None,
        "include_internal_token": True,
    }


@pytest.mark.asyncio
async def test_add_facts_sends_the_declared_language_in_the_body(monkeypatch) -> None:
    """The tag the extractor's model declared has to reach user-service.

    Until it was stored, a fact written in the wrong language was undetectable:
    recall never matched it and nothing recorded which language it was in.
    """
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured.update({"method": method, "path": path, **kwargs})
        return []

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    await UserServiceClient.add_facts_to_user("user-1", ["用户住在开塞利。"], language="zh-Hans")

    assert captured["json_body"] == {
        "contents": ["用户住在开塞利。"],
        "source": "auto_extracted",
        "language": "zh-Hans",
    }


@pytest.mark.asyncio
async def test_add_facts_omits_the_language_key_when_none_was_declared(monkeypatch) -> None:
    """Absent, not "". The column distinguishes "no language was declared"
    from a declared one, and an empty string would record a guess as though it
    were an observation."""
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    await UserServiceClient.add_facts_to_user("user-1", ["The user is 21."])

    assert "language" not in captured["json_body"]
