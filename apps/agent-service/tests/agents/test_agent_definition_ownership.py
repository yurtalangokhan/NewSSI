"""A flow may only reference agent definitions its runner is allowed to run.

AgentRef and Supervisor nodes resolve a definition straight out of the table
by id, and `_load_sub_agents_from_db` walks `sub_agent_ids` the same way. With
no ownership filter, putting someone else's definition id in a flow spec ran
their agent — their system prompt, their tool grants, their mail binding.

Definitions with no `created_by` are platform/seeded ones and stay shared;
only a definition owned by somebody else is withheld.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from agents.graphs.builder import GraphBuilder

MINE = uuid4()
THEIRS = uuid4()
SHARED = uuid4()


def _definition(agent_id, created_by, name):
    """A row shaped the way agent_def_to_config reads it."""
    return SimpleNamespace(
        id=agent_id,
        created_by=created_by,
        name=name,
        graph_schema="react",
        system_prompt="Be helpful.",
        model=None,
        mcp_tools=None,
        mcp_tool_configs=None,
        rag_config=None,
        supervisor_prompt=None,
        stages=None,
        pipeline_prompt=None,
        reflection_prompt=None,
        max_iterations=None,
        sub_agent_ids=None,
    )


class _Repo:
    """Stands in for AgentDefinitionRepository."""

    def __init__(self):
        self.rows = {
            MINE: _definition(MINE, "me", "mine"),
            THEIRS: _definition(THEIRS, "someone-else", "theirs"),
            SHARED: _definition(SHARED, None, "seeded"),
        }
        self.asked: list[tuple] = []

    async def get_by_id(self, agent_id):
        self.asked.append(("get_by_id", agent_id))
        return self.rows.get(agent_id)

    async def get_by_id_for_user(self, agent_id, owner_ids):
        self.asked.append(("get_by_id_for_user", agent_id, tuple(owner_ids)))
        row = self.rows.get(agent_id)
        if row is None:
            return None
        if row.created_by is None or row.created_by in owner_ids:
            return row
        return None


@pytest.mark.asyncio
async def test_sub_agent_loading_scopes_to_the_runner_when_owner_ids_are_known():
    repo = _Repo()
    builder = GraphBuilder(repository=repo, owner_ids=["me"])
    config: dict = {"sub_agent_ids": [str(THEIRS)]}

    await builder._load_sub_agents_from_db(config, target_field="sub_agents")

    assert config.get("sub_agents", []) == [], "another user's definition was loaded"
    assert any(call[0] == "get_by_id_for_user" for call in repo.asked)


@pytest.mark.asyncio
async def test_a_shared_definition_without_an_owner_is_still_loaded():
    repo = _Repo()
    builder = GraphBuilder(repository=repo, owner_ids=["me"])
    config: dict = {"sub_agent_ids": [str(SHARED)]}

    await builder._load_sub_agents_from_db(config, target_field="sub_agents")

    assert len(config.get("sub_agents", [])) == 1


@pytest.mark.asyncio
async def test_the_runners_own_definition_is_loaded():
    repo = _Repo()
    builder = GraphBuilder(repository=repo, owner_ids=["me"])
    config: dict = {"sub_agent_ids": [str(MINE)]}

    await builder._load_sub_agents_from_db(config, target_field="sub_agents")

    assert len(config.get("sub_agents", [])) == 1


@pytest.mark.asyncio
async def test_without_owner_ids_the_caller_is_trusted_to_have_authorised_already():
    """Internal callers that already authorised the whole graph pass no owner
    ids; the unscoped lookup stays available for them."""
    repo = _Repo()
    builder = GraphBuilder(repository=repo)
    config: dict = {"sub_agent_ids": [str(THEIRS)]}

    await builder._load_sub_agents_from_db(config, target_field="sub_agents")

    assert any(call[0] == "get_by_id" for call in repo.asked)
