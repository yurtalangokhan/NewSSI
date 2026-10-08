"""Historical migration and authoritative role-access regression tests."""

from pathlib import Path


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
