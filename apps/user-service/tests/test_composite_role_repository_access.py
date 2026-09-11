"""Regression tests for CompositeRoleRepository.get_access_by_names.

`get_access_by_names` resolves *composite* role names (system-admin,
enterprise-admin, enduser) which live in the `composite_roles` table.
Querying the `roles` table instead resolves nothing - `roles` holds the
fine-grained feature bundles (access-admin, agent-workspace-user, ...) -
so every user ends up with zero permissions and `is_admin=False`, which
surfaces in the web app as a redirect to /error/403 right after login.

The service-level tests mock this repository, so the table boundary is
only enforced here.
"""

import inspect
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.repository.role_repository import CompositeRoleRepository


def _get_access_source() -> str:
    return inspect.getsource(CompositeRoleRepository.get_access_by_names)


def test_get_access_by_names_resolves_composite_roles_not_feature_bundles():
    source = _get_access_source()

    assert "FROM composite_roles" in source
    # The existence lookup must not fall back to the feature-bundle table.
    assert "FROM roles" not in source


def test_get_access_by_names_reads_normalized_permission_and_hierarchy_tables():
    source = _get_access_source()

    assert "FROM role_permissions" in source
    assert "FROM role_hierarchy" in source
    assert "parent_role IN :names" in source


def test_normalized_role_tables_are_created_by_migration_0040():
    migration = (
        Path(__file__).parents[1] / "src/core/database/migrations/versions/0040_normalize_roles.py"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS role_permissions" in migration
    assert "CREATE TABLE IF NOT EXISTS role_hierarchy" in migration
    # Composite role direct permissions and bundle links must both be backfilled,
    # otherwise the resolver reads empty tables after the upgrade.
    assert "FROM composite_roles" in migration
    assert "INSERT INTO role_hierarchy" in migration


def test_custom_role_repair_migration_backfills_both_normalized_tables():
    migration = (
        Path(__file__).parents[1]
        / "src/core/database/migrations/versions/0043_repair_custom_role_access.py"
    ).read_text()

    assert "INSERT INTO role_permissions" in migration
    assert "jsonb_array_elements_text(composite_roles.permissions)" in migration
    assert "INSERT INTO role_hierarchy" in migration
    assert "jsonb_array_elements_text(composite_roles.role_ids)" in migration
    assert "ON CONFLICT DO NOTHING" in migration


@pytest.mark.asyncio
async def test_update_role_ids_keeps_normalized_hierarchy_in_sync():
    role = SimpleNamespace(
        name="Unit Manager",
        description=None,
        permissions=[],
        role_ids=[],
        is_builtin=False,
    )
    session = AsyncMock()
    session.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: role),
        None,
        None,
        None,
    ]

    repository = CompositeRoleRepository()

    @asynccontextmanager
    async def fake_session():
        yield session

    repository._session = fake_session

    await repository.update(
        "Unit Manager",
        role_ids=["account-self-service", "agent-workspace-user"],
    )

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert any("DELETE FROM role_hierarchy" in statement for statement in statements)
    hierarchy_inserts = [
        call
        for call in session.execute.await_args_list
        if "INSERT INTO role_hierarchy" in str(call.args[0])
    ]
    assert [call.args[1] for call in hierarchy_inserts] == [
        {"parent_role": "Unit Manager", "child_role": "account-self-service"},
        {"parent_role": "Unit Manager", "child_role": "agent-workspace-user"},
    ]
