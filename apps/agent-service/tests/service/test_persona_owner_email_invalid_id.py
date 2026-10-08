import pytest

from service.personas.persona_service import PersonaService


@pytest.mark.asyncio
async def test_get_personas_excludes_invalid_legacy_owner_ids_from_batch(
    monkeypatch, persona_factory
) -> None:
    service = PersonaService()
    valid_owner_id = "11111111-1111-4111-8111-111111111111"
    captured_ids: list[list[str]] = []

    async def fake_list_all(*, include_builtin: bool):
        assert include_builtin is False
        return [persona_factory(10, valid_owner_id), persona_factory(11, "dev-user")]

    async def fake_get_users_by_ids(user_ids: list[str]):
        captured_ids.append(user_ids)
        return [{"id": valid_owner_id, "email": "current@example.com"}]

    async def fake_availability(_agent: dict):
        return {"status": "available", "checks": []}

    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.list_all",
        staticmethod(fake_list_all),
    )
    monkeypatch.setattr("integrations.user_service_client.get_users_by_ids", fake_get_users_by_ids)
    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)

    personas = await service.get_personas()

    assert captured_ids == [[valid_owner_id]]
    assert personas[2]["owner"]["email"] == "current@example.com"
    assert personas[3]["owner"]["email"] == "Unknown user"
