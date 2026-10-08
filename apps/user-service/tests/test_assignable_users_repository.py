"""Candidate filtering over Keycloak identities and bulk group memberships."""

import uuid
from unittest.mock import AsyncMock

import httpx

from src.repository.user_repository import UserRepository


async def test_search_filters_scope_before_limit_and_counts_unique_users():
    root, child, outside, destination = [str(uuid.uuid4()) for _ in range(4)]
    people = [str(uuid.uuid4()) for _ in range(35)]
    users = [
        {
            "id": person,
            "email": f"person{i:02}@example.com",
            "firstName": "Alex",
            "lastName": "Tester",
            "username": f"person{i}",
        }
        for i, person in enumerate(people)
    ]
    memberships = {
        person: [outside if i < 30 else child] for i, person in enumerate(people) if i != 34
    }
    memberships[people[30]].append(root)
    memberships[people[31]].append(destination)
    organizations = {
        org: {"id": org, "name": org, "attributes": {}, "subGroupCount": 0}
        for org in (root, child, outside, destination)
    }
    organizations[root]["subGroups"] = [organizations[child], organizations[destination]]
    organizations[root]["subGroupCount"] = 2
    organizations[child]["parentId"] = root
    organizations[destination]["parentId"] = root

    async def request(method, path, **kwargs):
        path = path.split("?", 1)[0]
        if path == "/groups":
            value = list(organizations.values())
        elif path == "/groups/count":
            value = {"count": len(organizations)}
        elif path.endswith("/children"):
            value = organizations[path.split("/")[2]].get("subGroups", [])
        elif path == "/users":
            value = users
        elif path.endswith("/groups"):
            person = path.split("/")[2]
            value = [organizations[org] for org in memberships.get(person, [])]
        elif path.endswith("/members"):
            org = path.split("/")[2]
            value = [user for user in users if org in memberships.get(user["id"], [])]
        elif path.startswith("/groups/"):
            value = organizations[path.split("/")[2]]
        else:
            value = next(user for user in users if user["id"] == path.split("/")[2])
        return httpx.Response(
            200, json=value, request=httpx.Request(method, "https://kc.test" + path)
        )

    kc = AsyncMock()
    kc._keycloak_request.side_effect = request
    repo = UserRepository(keycloak=kc)
    repo._roles = AsyncMock(side_effect=AssertionError("Unexpected per-user role lookup"))
    matches, total = await repo.list_assignable(destination, root_ids=[root], query="Alex", limit=2)
    assert total == 3
    assert [user["id"] for user in matches] == [uuid.UUID(people[30]), uuid.UUID(people[32])]
    matches, total = await repo.list_assignable(destination, root_ids=None, query="person33")
    assert total == 1 and matches[0]["id"] == uuid.UUID(people[33])
    assert await repo.list_assignable(destination, root_ids=[]) == ([], 0)
    assert await repo.list_assignable(destination, root_ids=[root], user_id=people[0]) == ([], 0)
    matches, total = await repo.list_assignable(
        destination, root_ids=[root, outside], query="person00"
    )
    assert total == 1 and matches[0]["id"] == uuid.UUID(people[0])
    organizations[child]["attributes"]["agenticai.organization.is_active"] = ["false"]
    assert await repo.list_assignable(destination, root_ids=[root], user_id=people[33]) == ([], 0)
