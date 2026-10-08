"""Role statistics over the authoritative Keycloak identity inventory."""

import uuid
from unittest.mock import AsyncMock

from src.repository.user_repository import UserRepository


async def test_count_by_role_returns_role_and_count():
    repo = UserRepository(keycloak=AsyncMock())
    profiles = [{"id": str(uuid.UUID(int=i + 1))} for i in range(133)]

    async def pages(path):
        for row in profiles:
            yield row

    repo._pages = pages
    repo._role_index = AsyncMock(
        return_value={
            row["id"]: {"enduser" if i < 128 else "admin"} for i, row in enumerate(profiles)
        }
    )
    assert await repo.count_by_role() == [
        {"role": "enduser", "count": 128},
        {"role": "admin", "count": 5},
    ]


async def test_count_by_role_returns_empty_list_when_no_users():
    repo = UserRepository(keycloak=AsyncMock())

    async def pages(path):
        for row in []:
            yield row

    repo._pages = pages
    repo._role_index = AsyncMock(return_value={})
    assert await repo.count_by_role() == []


async def test_users_without_a_realm_role_are_counted_under_their_display_role():
    repo = UserRepository(keycloak=AsyncMock())
    profiles = [{"id": str(uuid.UUID(int=i + 1))} for i in range(3)]

    async def pages(path):
        for row in profiles:
            yield row

    repo._pages = pages
    repo._role_index = AsyncMock(return_value={profiles[0]["id"]: {"enduser"}})
    assert await repo.count_by_role() == [{"role": "enduser", "count": 3}]
