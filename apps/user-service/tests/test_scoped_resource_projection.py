"""Scoped saves must not rewrite unrelated Keycloak authorization objects."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repository.keycloak_resource_authorization import (
    ResourceAuthorizationProjectionRepository,
)


class Journal:
    def __init__(self):
        self.entries = {}

    async def smembers(self, key):
        return self.entries.get(key, set()).copy()

    async def sadd(self, key, *values):
        self.entries.setdefault(key, set()).update(values)

    async def delete(self, key):
        self.entries.pop(key, None)


class AuthorizationClient:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.next_id = 0
        self.fail_permission = False
        self.expected_client = "agent"

    async def client_id(self, name):
        assert name == f"{self.expected_client}-service"
        return f"{self.expected_client}-client"

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        assert f"{self.expected_client}-client" in path
        kind = path.split("/resource-server/")[1].split("/")[0]
        bucket = "resource" if kind == "resource" else "policy"
        objects = self.objects.setdefault(bucket, {})
        if method == "GET":
            name = kwargs["params"]["name"]
            return [dict(item) for item in objects.values() if name in item["name"]]
        if method == "DELETE":
            del objects[path.rsplit("/", 1)[1]]
            return None
        if method == "POST":
            if kind == "permission" and self.fail_permission:
                raise RuntimeError("Keycloak unavailable")
            self.next_id += 1
            identity = str(self.next_id)
            item = {**kwargs["json"], "_id" if bucket == "resource" else "id": identity}
            objects[identity] = item
            return item
        raise AssertionError(method)


def grant(resource="a", subject="org", level="read", resource_type="agent"):
    return {
        "resource_type": resource_type,
        "resource_id": resource,
        "organization_id": subject,
        "user_id": None,
        "permission_level": level,
    }


@pytest.fixture
def projection():
    client = AuthorizationClient()
    repo = ResourceAuthorizationProjectionRepository(client=client)
    repo.rows = [grant(), grant(subject="other"), grant("unrelated")]
    repo.journal = Journal()

    @asynccontextmanager
    async def locked():
        yield repo.journal

    repo._lock = locked
    repo._target_resource_ids = AsyncMock(return_value={"a"})

    async def inventory(resource_type=None, resource_ids=None):
        assert resource_type == "agent" and resource_ids is not None
        return [row for row in repo.rows if row["resource_id"] in resource_ids]

    repo.inventory = AsyncMock(side_effect=inventory)
    repo.clear = AsyncMock(side_effect=AssertionError("global clear"))
    repo.reconcile_all = AsyncMock(side_effect=AssertionError("global rebuild"))
    return repo


async def save(repo, mutation, desired=("a",)):
    return await repo.project_scoped_mutation(
        mutation,
        target_type="organization",
        target_id="org",
        resource_type="agent",
        desired_resource_ids=desired,
    )


@pytest.mark.asyncio
async def test_save_preserves_unrelated_objects_and_shared_subject_grants(projection):
    client = projection.client
    client.objects = {
        "policy": {
            "outside": {"id": "outside", "name": "agentic:instance:permission:agent:unrelated#read"}
        },
        "resource": {},
    }
    mutation = AsyncMock(return_value="saved")
    assert await save(projection, mutation) == "saved"
    assert client.objects["policy"]["outside"]["id"] == "outside"
    policies = list(client.objects["policy"].values())
    read = next(p for p in policies if p["name"].endswith("agent:a#read"))
    assert len(read["policies"]) == 2
    assert not projection.journal.entries
    projection.inventory.assert_awaited_once_with("agent", {"a"})


@pytest.mark.asyncio
async def test_retry_repairs_removed_resource_after_sql_commits(projection):
    async def remove():
        projection.rows = [grant(subject="other")]
        projection._target_resource_ids.return_value = set()
        return "saved"

    projection.client.fail_permission = True
    with pytest.raises(RuntimeError, match="Keycloak unavailable"):
        await save(projection, remove, desired=())
    assert projection.journal.entries
    projection.client.fail_permission = False
    await save(projection, AsyncMock(), desired=())
    policies = list(projection.client.objects["policy"].values())
    read = next(p for p in policies if p["name"].endswith("agent:a#read"))
    other = next(p for p in policies if p["name"] == "agentic:instance:group:other")
    assert read["policies"] == [other["id"]]
    assert not projection.journal.entries


@pytest.mark.asyncio
async def test_failed_sql_leaves_permissions_revoked_and_journal_for_retry(projection):
    await save(projection, AsyncMock())
    with pytest.raises(RuntimeError, match="SQL unavailable"):
        await save(projection, AsyncMock(side_effect=RuntimeError("SQL unavailable")))
    assert not any(
        p["name"].startswith("agentic:instance:permission:agent:a#")
        for p in projection.client.objects["policy"].values()
    )
    assert projection.journal.entries


@pytest.mark.asyncio
async def test_downgrade_removes_stronger_scopes(projection):
    projection.rows = [grant(level="admin")]
    await save(projection, AsyncMock())
    projection.rows = [grant(level="execute")]
    await save(projection, AsyncMock())
    names = [
        p["name"]
        for p in projection.client.objects["policy"].values()
        if p["name"].startswith("agentic:instance:permission:")
    ]
    assert names == ["agentic:instance:permission:agent:a#execute"]


@pytest.mark.asyncio
async def test_failed_clear_prevents_sql_mutation(projection):
    projection.client.request = AsyncMock(side_effect=RuntimeError("clear failed"))
    mutation = AsyncMock()
    with pytest.raises(RuntimeError, match="clear failed"):
        await save(projection, mutation)
    mutation.assert_not_awaited()
    assert projection.journal.entries


@pytest.mark.asyncio
async def test_revoke_last_grant_keeps_shared_objects_but_no_allow(projection):
    await save(projection, AsyncMock())
    projection.rows = []
    await save(projection, AsyncMock(), desired=())
    assert not any(p["type"] == "scope" for p in projection.client.objects["policy"].values())
    assert projection.client.objects["resource"]


@pytest.mark.asyncio
async def test_unrelated_assignment_count_does_not_increase_requests(projection):
    await save(projection, AsyncMock())
    projection.client.calls.clear()
    await save(projection, AsyncMock())
    baseline = len(projection.client.calls)
    projection.rows.extend(grant(f"unrelated-{n}") for n in range(1000))
    projection.client.calls.clear()
    await save(projection, AsyncMock())
    assert len(projection.client.calls) == baseline


@pytest.mark.asyncio
async def test_target_discovery_and_writes_are_inside_shared_lock(projection):
    import asyncio

    lock = asyncio.Lock()
    events = []

    @asynccontextmanager
    async def locked():
        async with lock:
            events.append("enter")
            yield projection.journal
            events.append("exit")

    async def discover(*_args):
        assert lock.locked()
        events.append("discover")
        await asyncio.sleep(0)
        return {"a"}

    async def mutation():
        assert lock.locked()
        events.append("sql")

    projection._lock = locked
    projection._target_resource_ids.side_effect = discover
    await asyncio.gather(save(projection, mutation), save(projection, mutation))
    assert events == ["enter", "discover", "sql", "exit"] * 2


@pytest.mark.asyncio
async def test_collection_save_only_uses_rag_client(projection):
    projection.client.expected_client = "rag"
    projection.inventory = AsyncMock(return_value=[grant(resource_type="rag_collection")])
    await projection.project_scoped_mutation(
        AsyncMock(),
        target_type="organization",
        target_id="org",
        resource_type="rag_collection",
        desired_resource_ids={"a"},
    )
    names = [p["name"] for p in projection.client.objects["policy"].values()]
    assert "agentic:instance:permission:rag_collection:a#read" in names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_type,column", [("organization", "organization_id"), ("user", "user_id")]
)
async def test_target_discovery_filters_type_subject_and_inheritance(target_type, column):
    from uuid import UUID

    repo = ResourceAuthorizationProjectionRepository(client=MagicMock())
    result = MagicMock()
    result.scalars.return_value = ["a", "b"]
    session = MagicMock(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def session_context():
        yield session

    repo._session = session_context
    assert await repo._target_resource_ids(target_type, UUID(int=1), "agent") == {"a", "b"}
    query = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert f"{column} =" in query
    assert "resource_type = 'agent'" in query
    assert "is_inherited IS false" in query


@pytest.mark.asyncio
async def test_journal_failure_prevents_keycloak_or_sql_writes(projection):
    projection.journal.sadd = AsyncMock(side_effect=RuntimeError("Redis unavailable"))
    mutation = AsyncMock()
    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await save(projection, mutation)
    mutation.assert_not_awaited()
    assert projection.client.calls == []
