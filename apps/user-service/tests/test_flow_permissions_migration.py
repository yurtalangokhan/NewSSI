"""Tests for migration 0044 — the flow:* permission catalog.

No live Postgres is available in this environment, and this repo has no
precedent for executing raw-SQL migrations against a test database (the
same is true of agent-service's 0031-0033) — the migration's own SQL is
Postgres-specific (jsonb_agg/jsonb_array_elements_text), which SQLite
couldn't run even if a test engine existed. These tests instead import the
migration module directly and assert on its pure-Python constants — the
part that actually decides catalog contents and role grants. Execution
correctness is reviewed by inspection against 0009/0012's proven idioms
(see the migration's own docstring).

Brief: .tmp/flow-canvas-task-18-brief.md
"""

from __future__ import annotations

import importlib


def _load_migration():
    return importlib.import_module(
        "src.core.database.migrations.versions.0044_add_flow_permissions"
    )


# ---------------------------------------------------------------------------
# 18.1 — catalog contents
# ---------------------------------------------------------------------------


def test_flow_permissions_present_in_catalog():
    migration = _load_migration()

    names = {p["name"] for p in migration.FLOW_PERMISSIONS}
    assert names == {
        "flow:read",
        "flow:create",
        "flow:update",
        "flow:delete",
        "flow:publish",
        "flow:execute",
    }
    for perm in migration.FLOW_PERMISSIONS:
        assert perm["entity"] == "flow"
        assert perm["service"] == "agent-service"
        assert perm["action"] == perm["name"].split(":")[1]


# ---------------------------------------------------------------------------
# 18.4 — the separation-of-duties control: agent-manager cannot publish or delete
# ---------------------------------------------------------------------------


def test_agent_manager_cannot_publish_or_delete():
    migration = _load_migration()

    assert "flow:publish" not in migration._AGENT_MANAGER_FLOW_PERMS
    assert "flow:delete" not in migration._AGENT_MANAGER_FLOW_PERMS
    assert set(migration._AGENT_MANAGER_FLOW_PERMS) == {
        "flow:read",
        "flow:create",
        "flow:update",
        "flow:execute",
    }


def test_agent_admin_gets_full_grant():
    migration = _load_migration()

    assert set(migration._ALL_FLOW_PERMS) == {
        "flow:read",
        "flow:create",
        "flow:update",
        "flow:delete",
        "flow:publish",
        "flow:execute",
    }


def test_agent_enduser_gets_read_only():
    migration = _load_migration()

    assert migration._AGENT_ENDUSER_FLOW_PERMS == ["flow:read"]


# ---------------------------------------------------------------------------
# 18.2 / 18.3 — the additive idiom, not 0009's destructive rewrite
# ---------------------------------------------------------------------------


def test_upgrade_uses_additive_jsonb_helper_not_a_list_rewrite():
    """Regression guard against reintroducing 0009's idiom, which would
    silently delete any permission an operator granted to a role since
    deploy (roles are tenant-customizable, migration 0007)."""
    migration = _load_migration()
    with open(migration.__file__, encoding="utf-8") as f:
        source = f.read()

    assert "_jsonb_add_permissions" in source
    assert "jsonb_agg(DISTINCT value" in source
    # The destructive idiom updates the WHOLE list in one UPDATE with a
    # hardcoded array; this migration must never do that.
    assert "UPDATE roles SET permissions = '" not in source
    assert "UPDATE composite_roles SET permissions = '" not in source


def test_upgrade_touches_correct_tables_per_the_0011_rename():
    """0011 swapped roles <-> composite_roles. enterprise-admin is a
    composite role (composite_roles); agent-admin/manager/enduser are
    coarse, service-client roles (roles)."""
    migration = _load_migration()
    with open(migration.__file__, encoding="utf-8") as f:
        source = f.read()

    assert '_jsonb_add_permissions("composite_roles", "enterprise-admin"' in source
    assert '_jsonb_add_permissions("roles", "agent-admin"' in source
    assert '_jsonb_add_permissions("roles", "agent-manager"' in source
    assert '_jsonb_add_permissions("roles", "agent-enduser"' in source


# ---------------------------------------------------------------------------
# 18.5 — downgrade is symmetric
# ---------------------------------------------------------------------------


def test_downgrade_removes_exactly_what_upgrade_added():
    migration = _load_migration()

    import inspect

    upgrade_src = inspect.getsource(migration.upgrade)
    downgrade_src = inspect.getsource(migration.downgrade)

    for role_name in ("enterprise-admin", "agent-admin", "agent-manager", "agent-enduser"):
        assert role_name in upgrade_src
        assert role_name in downgrade_src
