"""Removing view persistence leaves the organization hierarchy intact."""

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from src.api.routes.organizations_route import router
from src.core.database.models.base import Base


def test_layout_is_not_a_route_or_model():
    assert not any(route.path == "/organizations/layout" for route in router.routes)
    assert "organization_layouts" not in Base.metadata.tables


def test_drop_layout_preserves_hierarchy_and_downgrade_restores_empty_table(monkeypatch):
    migration = importlib.import_module(
        "src.core.database.migrations.versions.0048_drop_organization_layouts"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE organizations (id UUID PRIMARY KEY, parent_id UUID)"))
        connection.execute(
            text("INSERT INTO organizations VALUES ('root', NULL), ('child', 'root')")
        )
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.downgrade()
        connection.execute(
            text(
                "INSERT INTO organization_layouts (organization_id,position_x,position_y,created_at,updated_at) VALUES ('child',10,20,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        migration.upgrade()
        assert "organization_layouts" not in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT * FROM organizations ORDER BY id")).all() == [
            ("child", "root"),
            ("root", None),
        ]
        migration.downgrade()
        assert connection.execute(text("SELECT COUNT(*) FROM organization_layouts")).scalar() == 0
        assert {
            column["name"] for column in inspect(connection).get_columns("organization_layouts")
        } == {"organization_id", "position_x", "position_y", "created_at", "updated_at"}
