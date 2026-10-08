"""Per-user connector configurations: sealed at rest, readable only by services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from cryptography.fernet import InvalidToken
from error_contract import register_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.connector_configs_route import internal_router
from src.controller.user_connector_config_controller import UserConnectorConfigController
from src.core.security.encryption import SecretScope, get_cipher
from src.service.user_connector_config_service import UserConnectorConfigService

TOKEN = "internal-token-for-tests"
CONFIG = {"host": "db.internal", "username": "reader", "password": "s3cr3t-value"}


class FakeRepository:
    """In-memory stand-in for ``UserConnectorConfigRepository``."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, SimpleNamespace] = {}

    async def list_by_user(self, user_id):
        return [row for row in self.rows.values() if row.user_id == user_id]

    async def get(self, config_id, user_id):
        row = self.rows.get(config_id)
        return row if row is not None and row.user_id == user_id else None

    async def create(self, user_id, connector_name, name, config_encrypted):
        now = datetime.now(UTC)
        row = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            connector_name=connector_name,
            name=name,
            config_encrypted=config_encrypted,
            created_at=now,
            updated_at=now,
        )
        self.rows[row.id] = row
        return row

    async def update(self, config_id, user_id, **fields):
        row = await self.get(config_id, user_id)
        if row is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        return row

    async def delete(self, config_id, user_id):
        if await self.get(config_id, user_id) is None:
            return False
        del self.rows[config_id]
        return True


def _service() -> UserConnectorConfigService:
    service = UserConnectorConfigService.__new__(UserConnectorConfigService)
    service.repo = FakeRepository()
    return service


async def test_config_is_stored_as_one_ciphertext_and_read_back():
    service = _service()
    user_id = uuid.uuid4()

    meta = await service.create(user_id, "postgres", "warehouse", CONFIG)

    stored = next(iter(service.repo.rows.values())).config_encrypted
    assert "s3cr3t-value" not in stored and "db.internal" not in stored
    assert "config" not in meta and meta["connector_name"] == "postgres"

    detail = await service.get(uuid.UUID(meta["id"]), user_id)
    assert detail["config"] == CONFIG


async def test_another_user_cannot_read_update_or_delete_a_config():
    service = _service()
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    config_id = uuid.UUID((await service.create(owner, "postgres", "warehouse", CONFIG))["id"])

    assert await service.get(config_id, stranger) is None
    assert await service.update(config_id, stranger, name="mine now") is None
    assert await service.delete(config_id, stranger) is False
    assert await service.list_for_user(stranger) == []
    assert (await service.get(config_id, owner))["name"] == "warehouse"


async def test_update_reseals_the_config_and_keeps_it_out_of_the_response():
    service = _service()
    user_id = uuid.uuid4()
    config_id = uuid.UUID((await service.create(user_id, "postgres", "warehouse", CONFIG))["id"])
    before = service.repo.rows[config_id].config_encrypted

    meta = await service.update(config_id, user_id, config={**CONFIG, "password": "rotated"})

    assert "config" not in meta
    assert service.repo.rows[config_id].config_encrypted != before
    assert (await service.get(config_id, user_id))["config"]["password"] == "rotated"


async def test_connector_configs_are_sealed_under_their_own_scope():
    service = _service()
    await service.create(uuid.uuid4(), "postgres", "warehouse", CONFIG)
    stored = next(iter(service.repo.rows.values())).config_encrypted

    with pytest.raises(InvalidToken):
        get_cipher(SecretScope.SYSTEM_SETTINGS).decrypt(stored.encode())


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    controller = UserConnectorConfigController.__new__(UserConnectorConfigController)
    controller.service = _service()
    monkeypatch.setattr(
        "src.api.routes.connector_configs_route.get_user_connector_config_controller",
        lambda: controller,
    )
    app = FastAPI()
    register_error_handlers(app, service_name="user-service-test")
    app.include_router(internal_router, prefix="/api/v1")
    return TestClient(app)


def _internal() -> dict[str, str]:
    return {"X-Internal-Service-Token": TOKEN}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer some-user-jwt"}, {"X-Internal-Service-Token": "wrong"}],
)
def test_every_route_refuses_a_caller_without_the_internal_token(client, headers):
    base = f"/api/v1/internal/users/{uuid.uuid4()}/connector-configs"
    one = f"{base}/{uuid.uuid4()}"
    body = {"connector_name": "postgres", "name": "warehouse", "config": CONFIG}

    assert client.get(base, headers=headers).status_code == 403
    assert client.post(base, json=body, headers=headers).status_code == 403
    assert client.get(one, headers=headers).status_code == 403
    assert client.put(one, json={"name": "renamed"}, headers=headers).status_code == 403
    assert client.delete(one, headers=headers).status_code == 403


def test_internal_caller_round_trip(client):
    user_id = uuid.uuid4()
    base = f"/api/v1/internal/users/{user_id}/connector-configs"

    created = client.post(
        base,
        json={"connector_name": "postgres", "name": "warehouse", "config": CONFIG},
        headers=_internal(),
    )
    assert created.status_code == 201 and created.json()["statusCode"] == 201
    assert "config" not in created.json()["data"]
    one = f"{base}/{created.json()['data']['id']}"

    assert client.get(one, headers=_internal()).json()["data"]["config"] == CONFIG
    listed = client.get(base, headers=_internal()).json()["data"]
    assert [item["name"] for item in listed] == ["warehouse"]
    assert all("config" not in item for item in listed)

    renamed = client.put(one, json={"name": "renamed"}, headers=_internal())
    assert renamed.status_code == 200 and renamed.json()["data"]["name"] == "renamed"
    assert client.put(one, json={}, headers=_internal()).status_code == 422

    deleted = client.delete(one, headers=_internal())
    assert deleted.status_code == 200 and deleted.json()["data"] is None

    missing = client.get(one, headers=_internal())
    assert missing.status_code == 404 and missing.json()["statusCode"] == 404
    assert missing.json()["data"] is None and missing.json()["error"]["code"]
    assert client.delete(one, headers=_internal()).status_code == 404
