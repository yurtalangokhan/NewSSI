"""A thread belongs to the user whose id is stamped in its metadata.

Every /threads endpoint was guarded by a `thread:*` permission and nothing
else — and every enduser holds those permissions for their own threads. So
knowing a thread id was enough to read another user's conversation, rewrite
its metadata, or delete it outright. The ownership semantics (primary id plus
any legacy ids) already existed for the chat listing in
`service.user_helpers`; these endpoints simply never consulted them.
"""

from __future__ import annotations

import pytest
from fastapi import Request, Response

import api.routes.threads_route as threads_route
from schemas.threads import ThreadCreateRequest, ThreadSearchRequest, ThreadUpdateRequest
from service.threads import ThreadAccessService
from service.auth.auth_service import AuthenticatedUser

OWNER = AuthenticatedUser(user_id="owner-1", email="owner@example.com")
ATTACKER = AuthenticatedUser(user_id="attacker-9", email="attacker@example.com")

OWNED = {
    "thread_id": "t-owned",
    "metadata": {"user_id": "owner-1"},
    "status": "idle",
}
LEGACY_OWNED = {
    "thread_id": "t-legacy",
    "metadata": {"user_id": "someone-else", "legacy_user_ids": ["owner-1"]},
    "status": "idle",
}
FOREIGN = {
    "thread_id": "t-foreign",
    "metadata": {"user_id": "stranger-42"},
    "status": "idle",
}

_BY_ID = {t["thread_id"]: t for t in (OWNED, LEGACY_OWNED, FOREIGN)}


class _FakeService(ThreadAccessService):
    """Fake thread store; ownership filtering is the real service's own."""

    def __init__(self):
        self.deleted: list[str] = []
        self.updated: list[tuple[str, dict]] = []
        self.created: list[dict] = []

    async def get_thread(self, thread_id):
        return _BY_ID.get(thread_id)

    async def get_thread_state(self, thread_id):
        return {"thread_id": thread_id, "values": {}}

    async def list_threads(self, limit=100, offset=0, metadata=None):
        return list(_BY_ID.values())

    async def create_thread(self, thread_id=None, metadata=None):
        record = {"thread_id": thread_id or "new", "metadata": metadata or {}}
        self.created.append(record)
        return record

    async def update_thread(self, thread_id, metadata):
        self.updated.append((thread_id, metadata))
        return {"thread_id": thread_id, "metadata": metadata}

    async def delete_thread(self, thread_id):
        self.deleted.append(thread_id)
        return True



def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})


@pytest.fixture
def service(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(threads_route, "_get_service", lambda: fake)
    monkeypatch.setattr("service.threads.thread_access_service.get_checkpointer", lambda: None)
    return fake


@pytest.fixture(autouse=True)
def _identity_is_just_the_caller(monkeypatch):
    """No user-service round trip: the caller owns exactly their own id."""

    async def fake_owner_ids(request, user):
        return [user.user_id]

    monkeypatch.setattr("api.thread_access.resolve_owner_ids", fake_owner_ids)
    monkeypatch.setattr(threads_route, "resolve_owner_ids", fake_owner_ids)
    monkeypatch.setattr("service.threads.get_thread_access_service", lambda: _FakeService())


@pytest.mark.asyncio
async def test_owner_can_read_their_thread(service):
    result = await threads_route.get_thread(Response(), "t-owned", user=OWNER, request=_request())
    assert result.data == OWNED


@pytest.mark.asyncio
async def test_a_legacy_identity_still_reaches_its_own_thread(service):
    result = await threads_route.get_thread(Response(), "t-legacy", user=OWNER, request=_request())
    assert result.data == LEGACY_OWNED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda response: threads_route.get_thread(response, "t-foreign", user=ATTACKER, request=_request()),
        lambda response: threads_route.get_thread_state(response, "t-foreign", user=ATTACKER, request=_request()),
        lambda response: threads_route.update_thread(
            response, "t-foreign", ThreadUpdateRequest(metadata={"x": 1}), user=ATTACKER, request=_request()
        ),
        lambda response: threads_route.delete_thread(response, "t-foreign", user=ATTACKER, request=_request()),
    ],
)
async def test_another_user_gets_404_on_every_thread_endpoint(service, call):
    response = Response()
    result = await call(response)

    # A foreign thread is indistinguishable from a missing one: 404, never 403.
    assert response.status_code == 404
    assert result.statusCode == 404
    assert result.data is None
    assert service.deleted == []
    assert service.updated == []


@pytest.mark.asyncio
async def test_search_returns_only_the_callers_threads(service):
    found = await threads_route.search_threads(Response(), ThreadSearchRequest(), user=OWNER, request=_request())

    assert [t["thread_id"] for t in found.data] == ["t-owned", "t-legacy"]


@pytest.mark.asyncio
async def test_create_stamps_the_caller_as_owner_and_ignores_a_forged_one(service):
    await threads_route.create_thread(
        Response(),
        ThreadCreateRequest(thread_id="t-new", metadata={"user_id": "stranger-42"}),
        request=_request(),
        user=OWNER,
    )

    assert service.created[0]["metadata"]["user_id"] == OWNER.user_id
