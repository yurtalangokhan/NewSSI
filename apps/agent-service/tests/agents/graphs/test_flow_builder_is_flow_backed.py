"""``FlowGraphBuilder._is_flow_backed``: may a Supervisor node embed this agent?

Section 5.4 forbids a flow embedding another flow, so the builder has to tell a
flow-backed definition from a classic one before it compiles a Supervisor. The
predicate used to live in ``service.flows.resolvers``; reaching up to the
service layer for it was the one import that made ``agents`` and ``service``
depend on each other, so the builder now answers the question with the
repository it already holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from agents.graphs.flow import FlowGraphBuilder


@dataclass
class _FakeDefinition:
    id: object
    graph_schema: str


class _FakeAgentDefRepo:
    def __init__(self, definitions: list[_FakeDefinition]):
        self._definitions = definitions
        self.lookups: list[object] = []

    async def get_by_id(self, definition_id):
        self.lookups.append(definition_id)
        return next((d for d in self._definitions if d.id == definition_id), None)


@pytest.mark.asyncio
async def test_a_flow_backed_definition_is_recognised():
    flow_id = uuid4()
    repo = _FakeAgentDefRepo([_FakeDefinition(id=flow_id, graph_schema="flow")])
    builder = FlowGraphBuilder(repository=repo)

    assert await builder._is_flow_backed(str(flow_id)) is True


@pytest.mark.asyncio
async def test_a_classic_definition_is_not_flow_backed():
    classic_id = uuid4()
    repo = _FakeAgentDefRepo([_FakeDefinition(id=classic_id, graph_schema="react")])
    builder = FlowGraphBuilder(repository=repo)

    assert await builder._is_flow_backed(str(classic_id)) is False


@pytest.mark.asyncio
async def test_an_unknown_definition_id_is_not_flow_backed():
    repo = _FakeAgentDefRepo([])
    builder = FlowGraphBuilder(repository=repo)

    assert await builder._is_flow_backed(str(uuid4())) is False


@pytest.mark.asyncio
async def test_a_built_in_agent_id_never_reaches_the_repository():
    """Built-in ids are not UUIDs; answering False must cost no DB round trip."""
    repo = _FakeAgentDefRepo([])
    builder = FlowGraphBuilder(repository=repo)

    assert await builder._is_flow_backed("not-a-uuid") is False
    assert repo.lookups == []
