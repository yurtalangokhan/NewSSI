"""Tests for migration 0049 — flow:* defaults on the canonical composite roles.

Same approach as test_flow_permissions_migration.py: no live Postgres in
this environment, so these assert on the migration module's pure-Python
constants and source, not by executing the SQL against a real database.
"""

from __future__ import annotations

import importlib
import inspect


def _load_migration():
    return importlib.import_module(
        "src.core.database.migrations.versions.0049_fix_canonical_role_flow_permissions"
    )


def test_system_admin_and_enterprise_admin_get_full_grant():
    migration = _load_migration()

    assert set(migration._ALL_FLOW_PERMS) == {
        "flow:read",
        "flow:create",
        "flow:update",
        "flow:delete",
        "flow:publish",
        "flow:execute",
    }


def test_enduser_gets_read_and_execute_only():
    migration = _load_migration()

    assert set(migration._ENDUSER_FLOW_PERMS) == {"flow:read", "flow:execute"}
    assert "flow:create" not in migration._ENDUSER_FLOW_PERMS
    assert "flow:update" not in migration._ENDUSER_FLOW_PERMS
    assert "flow:delete" not in migration._ENDUSER_FLOW_PERMS
    assert "flow:publish" not in migration._ENDUSER_FLOW_PERMS


def test_upgrade_grants_correct_roles():
    migration = _load_migration()
    upgrade_src = inspect.getsource(migration.upgrade)

    assert '_add_role_permissions("system-admin", _ALL_FLOW_PERMS)' in upgrade_src
    assert '_add_role_permissions("enterprise-admin", _ALL_FLOW_PERMS)' in upgrade_src
    assert '_add_role_permissions("enduser", _ENDUSER_FLOW_PERMS)' in upgrade_src


def test_upgrade_writes_role_permissions_not_the_unread_jsonb_column():
    """Regression guard: CompositeRoleRepository.get_access_by_names() reads
    the normalized role_permissions/role_hierarchy tables exclusively and
    never looks at composite_roles.permissions/role_ids (JSONB) -- writing
    to the JSONB column (as this migration originally did) is a silent
    no-op against real permission resolution."""
    migration = _load_migration()
    upgrade_src = inspect.getsource(migration.upgrade)
    helpers_src = inspect.getsource(migration._add_role_permissions)

    assert "INSERT INTO role_permissions" in helpers_src
    assert "ON CONFLICT (role_name, permission_name) DO NOTHING" in helpers_src
    assert "composite_roles" not in upgrade_src
    assert "composite_roles" not in helpers_src


def test_downgrade_removes_exactly_what_upgrade_added_and_leaves_enterprise_admin_alone():
    """enterprise-admin's grant is owned by 0044's downgrade; this
    migration's downgrade must not double-manage it."""
    migration = _load_migration()

    upgrade_src = inspect.getsource(migration.upgrade)
    downgrade_src = inspect.getsource(migration.downgrade)

    for role_name in ("system-admin", "enduser"):
        assert role_name in upgrade_src
        assert role_name in downgrade_src

    assert "enterprise-admin" not in downgrade_src
