import logging

import pytest

from controller.persona_controller import PersonaController


@pytest.mark.asyncio
async def test_get_personas_enriches_distinct_local_owners_in_one_batch_request(
    monkeypatch, persona_factory
) -> None:
    controller = PersonaController()
    local_owner_id = "11111111-1111-4111-8111-111111111111"
    missing_owner_id = "22222222-2222-4222-8222-222222222222"
    captured_ids: list[list[str]] = []

    async def fake_list_all(*, include_builtin: bool):
        assert include_builtin is False
        return [
            persona_factory(10, local_owner_id),
            persona_factory(11, local_owner_id),
            persona_factory(12, missing_owner_id),
            persona_factory(13, "legacy@example.com"),
        ]

    async def fake_get_users_by_ids(user_ids: list[str]):
        captured_ids.append(user_ids)
        return [{"id": local_owner_id, "email": "current@example.com"}]

    async def fake_availability(_agent: dict):
        return {"status": "available", "checks": []}

    monkeypatch.setattr("controller.persona_controller.PersonaDB.list_all", fake_list_all)
    monkeypatch.setattr("service.UserServiceClient.get_users_by_ids", fake_get_users_by_ids)
    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    personas = await controller.get_personas()
    custom_personas = personas[2:]

    assert captured_ids == [[local_owner_id, missing_owner_id]]
    assert [(persona["owner"]["id"], persona["owner"]["email"]) for persona in custom_personas] == [
        (local_owner_id, "current@example.com"),
        (local_owner_id, "current@example.com"),
        (missing_owner_id, "Unknown user"),
        ("legacy@example.com", "legacy@example.com"),
    ]


@pytest.mark.asyncio
async def test_get_personas_uses_unknown_user_when_owner_batch_lookup_fails(
    monkeypatch, caplog, persona_factory
) -> None:
    controller = PersonaController()
    owner_id = "11111111-1111-4111-8111-111111111111"

    async def fake_list_all(*, include_builtin: bool):
        assert include_builtin is False
        return [persona_factory(10, owner_id)]

    async def failing_get_users_by_ids(_user_ids: list[str]):
        raise RuntimeError("user-service unavailable")

    async def fake_availability(_agent: dict):
        return {"status": "available", "checks": []}

    monkeypatch.setattr("controller.persona_controller.PersonaDB.list_all", fake_list_all)
    monkeypatch.setattr("service.UserServiceClient.get_users_by_ids", failing_get_users_by_ids)
    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    with caplog.at_level(logging.WARNING):
        personas = await controller.get_personas()

    assert personas[2]["owner"] == {"id": owner_id, "email": "Unknown user"}
    assert "Failed to resolve persona owner emails" in caplog.text
