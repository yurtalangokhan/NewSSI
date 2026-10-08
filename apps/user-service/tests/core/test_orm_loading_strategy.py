"""Relationships must be loaded explicitly, not eagerly on every query.

Spec 5/T5: every relationship on User and Organization was `lazy="selectin"`,
so loading a single user issued a SELECT per relationship (five extra
round-trips for a permission check that never even reads them), and the
engine used NullPool, opening a fresh physical connection per repository
call instead of reusing a pooled one.
"""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.pool import NullPool


def test_identity_tables_are_not_registered_in_application_metadata():
    from src.core.database.models import Base

    assert not {"users", "organizations", "user_organizations", "role_permissions", "role_hierarchy"}.intersection(Base.metadata.tables)


def test_application_models_do_not_eagerly_load_identity_relationships():
    from src.core.database.models import AuditLogModel, ResourcePermissionModel

    for model in (AuditLogModel, ResourcePermissionModel):
        assert not list(sa_inspect(model).relationships)


def test_engine_does_not_use_nullpool():
    from src.core.database.engine import get_db_engine

    assert not isinstance(get_db_engine().pool, NullPool)


def test_engine_enables_pre_ping():
    from src.core.database.engine import get_db_engine

    assert get_db_engine().pool._pre_ping is True
