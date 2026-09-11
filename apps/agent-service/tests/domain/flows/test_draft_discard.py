"""Draft discard (DELETE .../flow/draft) — repository + service behavior.

Mirrors the existing flow-version test style: the repository is exercised
through a fake session-backed double, not a live database.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.flows.service import FlowService


class _FakeVersionRepo:
    def __init__(self, has_draft: bool):
        self.has_draft = has_draft
        self.deleted_for = None

    async def delete_draft(self, definition_id):
        self.deleted_for = definition_id
        if not self.has_draft:
            return False
        self.has_draft = False
        return True


@pytest.mark.asyncio
async def test_discard_draft_returns_true_when_draft_existed():
    definition_id = uuid4()
    repo = _FakeVersionRepo(has_draft=True)
    service = FlowService(repository=None, version_repository=repo)

    assert await service.discard_draft(definition_id) is True
    assert repo.deleted_for == definition_id


@pytest.mark.asyncio
async def test_discard_draft_is_idempotent_when_no_draft():
    repo = _FakeVersionRepo(has_draft=False)
    service = FlowService(repository=None, version_repository=repo)

    assert await service.discard_draft(uuid4()) is False


@pytest.mark.asyncio
async def test_route_discard_draft_emits_audit_only_when_deleted(monkeypatch):
    from api.routes import FlowVersionsRoute

    definition_id = uuid4()
    emitted = []

    class _Emitter:
        async def emit(self, event, def_id, **kwargs):
            emitted.append((event, def_id))

    class _Service:
        def __init__(self, result):
            self.result = result

        async def discard_draft(self, _definition_id):
            return self.result

    monkeypatch.setattr(FlowVersionsRoute, "get_flow_audit_emitter", lambda: _Emitter())

    monkeypatch.setattr(FlowVersionsRoute, "_get_service", lambda: _Service(True))
    await FlowVersionsRoute.discard_draft(definition_id, user=object())
    assert emitted == [("flow:draft_discarded", definition_id)]

    emitted.clear()
    monkeypatch.setattr(FlowVersionsRoute, "_get_service", lambda: _Service(False))
    await FlowVersionsRoute.discard_draft(definition_id, user=object())
    assert emitted == []
