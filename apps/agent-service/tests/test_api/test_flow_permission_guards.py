"""Tests that flow routes are guarded by flow:* permissions, not the
interim agent:* ones P1 Task 6 and P3 Tasks 16/17 used as placeholders
(documented at the time: "do not invent flow:* checks before the catalog
exists" — user-service migration 0018, Task 18, is what makes them safe to
use now).

require_permission(permission) returns a closure over `permission`; rather
than round-tripping full HTTP requests (which the dev-user auth bypass
would make indistinguishable regardless of which permission string is
checked), these tests inspect the closure directly — a real, precise
signal that each route's dependency object was constructed with the
expected string.

Brief: .tmp/flow-canvas-task-18-brief.md
"""

from __future__ import annotations

import api.routes.AgentDefinitionsRoute as agent_definitions_route
import api.routes.FlowComponentsRoute as flow_components_route
import api.routes.FlowVersionsRoute as flow_versions_route


def _permission_of(dependency) -> str:
    """Extract the permission string require_permission(...) closed over."""
    names = dependency.__code__.co_freevars
    return dependency.__closure__[names.index("permission")].cell_contents


# ---------------------------------------------------------------------------
# FlowComponentsRoute
# ---------------------------------------------------------------------------


def test_list_components_requires_flow_read():
    assert _permission_of(flow_components_route._require_list) == "flow:read"


def test_get_component_and_resolve_options_require_flow_read():
    assert _permission_of(flow_components_route._require_read) == "flow:read"


# ---------------------------------------------------------------------------
# AgentDefinitionsRoute — /validate-flow
# ---------------------------------------------------------------------------


def test_validate_flow_requires_flow_read():
    import inspect

    source = inspect.getsource(agent_definitions_route.validate_flow)
    assert 'require_permission("flow:read")' in source


# ---------------------------------------------------------------------------
# FlowVersionsRoute
# ---------------------------------------------------------------------------


def test_get_and_list_draft_endpoints_require_flow_read():
    assert _permission_of(flow_versions_route._require_read) == "flow:read"


def test_save_draft_requires_flow_update():
    assert _permission_of(flow_versions_route._require_update) == "flow:update"


def test_publish_requires_flow_publish():
    assert _permission_of(flow_versions_route._require_publish) == "flow:publish"


def test_rollback_requires_flow_publish():
    import inspect

    source = inspect.getsource(flow_versions_route.rollback_flow)
    assert "_require_publish" in source


# ---------------------------------------------------------------------------
# 18.6 — constraint #1 applied to auth: classic agent:* guards unchanged
# ---------------------------------------------------------------------------


def test_classic_agent_definition_endpoints_keep_their_own_permissions():
    """Only /validate-flow's guard changed in P3 — every classic
    create/list/read/update/delete/composition endpoint keeps exactly the
    agent:* permission it had before P3, unaffected by the flow:* catalog.
    (2026-08-27, agent-flow-expansion: /expand added as a second
    agent:create route — it creates new AgentDefinitionModel rows for a
    Supervisor's cloned sub-agents, matching the same permission the
    existing create endpoint already requires.)"""
    import inspect

    source = inspect.getsource(agent_definitions_route)

    assert source.count('require_permission("agent:list")') == 4
    assert source.count('require_permission("agent:create")') == 2
    assert source.count('require_permission("agent:read")') == 4
    assert source.count('require_permission("agent:update")') == 2
    assert source.count('require_permission("agent:delete")') == 1
    assert source.count('require_permission("flow:read")') == 1  # validate-flow, only
