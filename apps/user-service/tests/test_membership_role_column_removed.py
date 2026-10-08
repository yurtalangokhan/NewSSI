from src.core.database.models.base import Base
from src.repository import UserOrganizationRepository
from tests.test_keycloak_organizations import CHILD, USER, Admin


def test_membership_has_no_role_storage():
    assert "user_organizations" not in Base.metadata.tables
    assert "organizations" not in Base.metadata.tables
    assert "users" not in Base.metadata.tables


async def test_membership_serializes_without_legacy_attribute():
    repository = UserOrganizationRepository(Admin())
    result = await repository.set_primary(USER, CHILD)
    assert "role_in_org" not in result
    assert result["is_primary"] and result["is_active"]


def test_migration_drops_only_obsolete_role_storage(monkeypatch):
    import importlib
    from unittest.mock import MagicMock

    migration = importlib.import_module(
        "src.core.database.migrations.versions.0046_drop_membership_role"
    )
    execute, drop_column = MagicMock(), MagicMock()
    monkeypatch.setattr(migration.op, "execute", execute)
    monkeypatch.setattr(migration.op, "drop_column", drop_column)
    migration.upgrade()
    drop_column.assert_called_once_with("user_organizations", "role_in_org")
    assert [call.args[0] for call in execute.call_args_list] == [
        "DROP INDEX IF EXISTS idx_user_org_role",
        "DROP INDEX IF EXISTS ix_user_organizations_role_in_org",
    ]
