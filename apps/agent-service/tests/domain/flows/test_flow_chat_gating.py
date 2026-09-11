"""A flow with no published version must not be chattable.

The gate lives outside the agent factory on purpose: a caller hitting the
chat API directly (no UI) has to be refused too, with a meaningful status
rather than the factory's generic "no flow_spec" ValueError.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.exceptions import FlowNotPublishedError
from domain.flows.gating import assert_flow_chat_ready


class _Definition:
    def __init__(self, graph_schema, published_flow_version_id):
        self.id = uuid4()
        self.graph_schema = graph_schema
        self.published_flow_version_id = published_flow_version_id


class _Repo:
    def __init__(self, definition):
        self.definition = definition

    async def get_by_persona_id(self, _persona_id):
        return self.definition


@pytest.mark.asyncio
async def test_unpublished_flow_is_refused():
    repo = _Repo(_Definition("flow", None))
    with pytest.raises(FlowNotPublishedError):
        await assert_flow_chat_ready(42, repository=repo)


@pytest.mark.asyncio
async def test_published_flow_is_allowed():
    repo = _Repo(_Definition("flow", uuid4()))
    await assert_flow_chat_ready(42, repository=repo)


@pytest.mark.asyncio
async def test_non_flow_agent_is_never_gated():
    repo = _Repo(_Definition("zero_shot", None))
    await assert_flow_chat_ready(42, repository=repo)


@pytest.mark.asyncio
async def test_missing_definition_is_not_gated():
    repo = _Repo(None)
    await assert_flow_chat_ready(42, repository=repo)


@pytest.mark.asyncio
async def test_route_maps_gate_failure_to_409():
    from fastapi import HTTPException, status

    try:
        raise FlowNotPublishedError(7)
    except FlowNotPublishedError as exc:
        mapped = HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "FLOW_NOT_PUBLISHED", "message": str(exc)},
        )

    assert mapped.status_code == 409
    assert mapped.detail["code"] == "FLOW_NOT_PUBLISHED"
