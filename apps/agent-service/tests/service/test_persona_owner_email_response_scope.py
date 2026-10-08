import uuid

import pytest

from service.personas.persona_service import PersonaService


@pytest.mark.asyncio
async def test_custom_persona_serialization_resolves_owner_without_preloaded_map(
    monkeypatch, persona_factory
) -> None:
    service = PersonaService()
    owner_id = "11111111-1111-4111-8111-111111111111"
    captured_ids: list[list[str]] = []

    async def fake_get_users_by_ids(user_ids: list[str]):
        captured_ids.append(user_ids)
        return [{"id": owner_id, "email": "current@example.com"}]

    async def fake_availability(_agent: dict):
        return {"status": "available", "checks": []}

    monkeypatch.setattr("integrations.user_service_client.get_users_by_ids", fake_get_users_by_ids)
    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)

    serialized = await service._serialize_custom_persona(persona_factory(10, owner_id))

    assert captured_ids == [[owner_id]]
    assert serialized["owner"] == {"id": owner_id, "email": "current@example.com"}


@pytest.mark.asyncio
async def test_get_personas_caps_owner_batch_at_endpoint_limit(
    monkeypatch, persona_factory
) -> None:
    service = PersonaService()
    owner_ids = [str(uuid.UUID(int=index + 1)) for index in range(101)]
    captured_ids: list[list[str]] = []

    async def fake_list_all(*, include_builtin: bool):
        assert include_builtin is False
        return [persona_factory(index + 10, owner_id) for index, owner_id in enumerate(owner_ids)]

    async def fake_get_users_by_ids(user_ids: list[str]):
        captured_ids.append(user_ids)
        return [
            {"id": owner_id, "email": f"owner-{index}@example.com"}
            for index, owner_id in enumerate(user_ids)
        ]

    async def fake_availability(_agent: dict):
        return {"status": "available", "checks": []}

    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.list_all",
        staticmethod(fake_list_all),
    )
    monkeypatch.setattr("integrations.user_service_client.get_users_by_ids", fake_get_users_by_ids)
    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)

    personas = await service.get_personas()

    assert captured_ids == [owner_ids[:100]]
    assert personas[2]["owner"]["email"] == "owner-0@example.com"
    assert personas[-1]["owner"]["email"] == "Unknown user"
