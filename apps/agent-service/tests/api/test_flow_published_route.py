"""GET /agent-definitions/{id}/flow/published — the chat flow-preview panel
reads this (not /flow/draft) so it always shows what actually executes."""

from uuid import uuid4

import pytest
from error_contract import NotFoundError

from service.auth.auth_service import AuthenticatedUser


class _FakePublishedVersion:
    def __init__(self, flow_spec: dict) -> None:
        self.flow_spec = flow_spec


class _FakeVersionRepo:
    def __init__(self, published: dict | None) -> None:
        self._published = published

    async def get_published(self, _definition_id):
        if self._published is None:
            return None
        return _FakePublishedVersion(self._published)


def _flow_spec_dict() -> dict:
    return {
        "nodes": [
            {"id": "ChatInput-1", "type": "ChatInput", "position": {"x": 0, "y": 0}, "values": {}},
            {
                "id": "ChatOutput-1",
                "type": "ChatOutput",
                "position": {"x": 100, "y": 0},
                "values": {},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "ChatInput-1",
                "target": "ChatOutput-1",
                "sourceHandle": "output",
                "targetHandle": "input",
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-1", email="user@example.com")


@pytest.mark.asyncio
async def test_returns_the_published_spec(monkeypatch):
    from service.flows.flow_versions_application_service import FlowVersionsApplicationService
    from infrastructure.db.repositories import flow_version_repo as repo_module

    monkeypatch.setattr(
        repo_module,
        "FlowVersionRepository",
        lambda: _FakeVersionRepo(_flow_spec_dict()),
    )

    body = await FlowVersionsApplicationService().get_published(uuid4())

    assert [n["id"] for n in body["nodes"]] == ["ChatInput-1", "ChatOutput-1"]


@pytest.mark.asyncio
async def test_404_when_nothing_published(monkeypatch):
    from service.flows.flow_versions_application_service import FlowVersionsApplicationService
    from infrastructure.db.repositories import flow_version_repo as repo_module

    monkeypatch.setattr(repo_module, "FlowVersionRepository", lambda: _FakeVersionRepo(None))

    with pytest.raises(NotFoundError) as exc_info:
        await FlowVersionsApplicationService().get_published(uuid4())

    assert exc_info.value.status_code == 404
