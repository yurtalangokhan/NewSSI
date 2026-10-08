"""Offline identity cutover checks must reject ambiguous or incomplete input."""

import importlib.util
from uuid import UUID

import pytest


def cutover():
    assert importlib.util.find_spec("src.core.database.identity_cutover") is not None
    from src.core.database import identity_cutover

    return identity_cutover


OLD = str(UUID(int=1))
NEW = str(UUID(int=2))
ORG = str(UUID(int=3))
GROUP = str(UUID(int=4))


def manifest():
    return {
        "version": 1,
        "realm": "platform",
        "users": {OLD: NEW},
        "organizations": {ORG: GROUP},
        "keycloak_user_ids": [NEW],
        "keycloak_group_ids": [GROUP],
        "external_references_verified": True,
        "keycloak_assignments_verified": True,
    }


def test_cutover_maps_explicit_ids_and_preserves_authoritative_subjects():
    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    assert plan.resolve("users", OLD) == NEW
    assert plan.resolve("users", NEW) == NEW
    assert plan.resolve("organizations", ORG) == GROUP


@pytest.mark.parametrize("field", ["external_references_verified", "keycloak_assignments_verified"])
def test_cutover_requires_preflight_evidence(field):
    data = manifest()
    data[field] = False
    with pytest.raises(ValueError, match=field):
        cutover().validate_manifest(data, [(OLD, NEW)], [ORG])


def test_cutover_refuses_missing_group_mapping():
    data = manifest()
    data["organizations"] = {}
    with pytest.raises(ValueError, match="organizations"):
        cutover().validate_manifest(data, [(OLD, NEW)], [ORG])


def test_cutover_refuses_mismatch_with_recorded_keycloak_id():
    with pytest.raises(ValueError, match="recorded"):
        cutover().validate_manifest(manifest(), [(OLD, GROUP)], [ORG])


def test_cutover_refuses_unknown_target_and_identity_merges():
    data = manifest()
    data["keycloak_user_ids"] = []
    with pytest.raises(ValueError, match="Keycloak"):
        cutover().validate_manifest(data, [(OLD, NEW)], [ORG])
    data = manifest()
    data["users"][GROUP] = NEW
    with pytest.raises(ValueError, match="merge"):
        cutover().validate_manifest(data, [(OLD, NEW), (GROUP, NEW)], [ORG])


def test_cutover_refuses_unknown_retained_reference():
    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    with pytest.raises(ValueError, match="Unresolved"):
        plan.resolve("users", str(UUID(int=99)))


def test_retained_updates_only_include_present_legacy_references():
    from src.core.database.identity_cutover import retained_reference_changes

    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    # The import can have 100k users while an application table has only one owner.
    plan.mappings["users"].update(
        {str(UUID(int=i)): str(UUID(int=i + 10000)) for i in range(100, 1100)}
    )
    assert retained_reference_changes(plan, "users", [OLD, NEW, OLD]) == {OLD: NEW}
    assert retained_reference_changes(plan, "users", []) == {}
    with pytest.raises(ValueError, match="Unresolved"):
        retained_reference_changes(plan, "users", [str(UUID(int=99))])


@pytest.mark.parametrize(
    "kind,discriminator,old,new",
    [
        ("users", "user", OLD, NEW),
        ("organizations", "organization", ORG, GROUP),
    ],
)
def test_historical_audit_targets_preserve_deleted_ids_and_remap_known_ids(
    kind, discriminator, old, new
):
    module = cutover()
    plan = module.validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    deleted = str(UUID(int=99))
    reference = ("permission_audit_logs", "target_id", kind, discriminator)
    changes, historical = module.retained_reference_plan(
        plan, reference, [old, new, deleted, deleted]
    )
    assert changes == {old: new}
    assert historical == [
        {
            "table": "permission_audit_logs",
            "column": "target_id",
            "target_type": discriminator,
            "identity_kind": kind,
            "target_id": deleted,
            "reason": "historical_target_not_in_source_or_keycloak",
        }
    ]
    with pytest.raises(ValueError, match="Unresolved"):
        plan.resolve(kind, deleted)
    with pytest.raises(ValueError):
        module.retained_reference_plan(plan, reference, ["not-an-identity-uuid"])


def test_historical_target_exception_never_allows_unknown_owners_or_access_references():
    module = cutover()
    plan = module.validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    references = [
        ref for ref in module.REFERENCES if ref[:2] != ("permission_audit_logs", "target_id")
    ]
    references.append(("permission_audit_logs", "target_id", "users", "organization"))
    for reference in references:
        with pytest.raises(ValueError, match="Unresolved"):
            module.retained_reference_plan(plan, reference, [str(UUID(int=99))])


def test_retained_models_have_no_local_identity_foreign_keys():
    from src.core.database.models import Base

    retained = ("api_keys", "audit_logs", "user_settings", "user_memory", "resource_permissions")
    for name in retained:
        assert not Base.metadata.tables[name].foreign_keys


def test_reference_transform_changes_only_registered_identity_fields():
    from src.core.database.identity_cutover import remap_reference_value

    mapping = {OLD: NEW}
    assert remap_reference_value([OLD, NEW], mapping, "array") == [NEW, NEW]
    assert remap_reference_value({"user_id": OLD, "prompt": OLD}, mapping, "user_id") == {
        "user_id": NEW,
        "prompt": OLD,
    }
    assert remap_reference_value({"owner_id": OLD}, mapping, "owner_id") == {"owner_id": NEW}
    assert remap_reference_value("internal-service", mapping, "scalar") == "internal-service"


def test_external_database_reconciliation_is_transactional_and_idempotent():
    import sqlalchemy as sa

    from src.core.database.identity_cutover import reconcile_external_database

    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "thread",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("metadata", sa.JSON),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(table.insert().values(id=1, metadata={"user_id": OLD, "text": OLD}))
        assert reconcile_external_database(connection, plan, apply=False) == 1
        assert connection.execute(sa.select(table.c.metadata)).scalar()["user_id"] == OLD
        assert reconcile_external_database(connection, plan, apply=True) == 1
        assert reconcile_external_database(connection, plan, apply=False) == 0
        assert connection.execute(sa.select(table.c.metadata)).scalar() == {
            "user_id": NEW,
            "text": OLD,
        }


def test_external_database_reconciliation_rejects_unmapped_owner():
    import sqlalchemy as sa

    from src.core.database.identity_cutover import reconcile_external_database

    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE project (id INTEGER PRIMARY KEY, user_id TEXT)"))
        connection.execute(sa.text("INSERT INTO project VALUES (1, 'unknown-user')"))
        with pytest.raises(ValueError, match="Unresolved"):
            reconcile_external_database(connection, plan, apply=True)


def test_retained_models_configure_without_identity_tables():
    from sqlalchemy.orm import configure_mappers

    from src.core.database.models import Base

    configure_mappers()
    assert not set(cutover().IDENTITY_TABLES).intersection(Base.metadata.tables)


def test_destructive_revision_refuses_missing_manifest(monkeypatch):
    import importlib

    migration = importlib.import_module(
        "src.core.database.migrations.versions.0049_keycloak_identity_cutover"
    )
    monkeypatch.setattr(migration.context, "get_x_argument", lambda **kwargs: {})
    with pytest.raises(ValueError, match="identity_manifest"):
        migration.upgrade()


@pytest.mark.asyncio
async def test_keycloak_inventory_paginates_and_queries_nested_groups():
    from src.core.database.reconcile_identity import _inventory

    class Response:
        def __init__(self, value):
            self.value = value

        def raise_for_status(self):
            pass

        def json(self):
            return self.value

    class Keycloak:
        async def _keycloak_request(self, method, path, **kwargs):
            if path == "/users":
                first = kwargs["params"]["first"]
                return Response(
                    [{"id": str(UUID(int=i + 1))} for i in range(100)] if first == 0 else []
                )
            if path == "/groups":
                return Response([{"id": ORG}])
            if path == f"/groups/{ORG}/children":
                return Response([{"id": GROUP}])
            return Response([])

    users, groups = await _inventory(Keycloak())
    assert len(users) == 100
    assert groups == [ORG, GROUP]


def test_snapshot_digest_is_row_order_independent_and_detects_changes():
    snapshot = {"users": [{"id": OLD}, {"id": NEW}]}
    first = cutover().snapshot_digest(snapshot)
    snapshot["users"].reverse()
    assert cutover().snapshot_digest(snapshot) == first
    snapshot["users"][0]["email"] = "changed@example.com"
    assert cutover().snapshot_digest(snapshot) != first


def test_external_reconciliation_refuses_unregistered_identity_columns():
    import sqlalchemy as sa

    from src.core.database.identity_cutover import reconcile_external_database

    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    with sa.create_engine("sqlite://").begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE custom_resource (id INTEGER PRIMARY KEY, owner_id TEXT)")
        )
        with pytest.raises(ValueError, match="Unregistered"):
            reconcile_external_database(connection, plan, apply=True)


def test_explicit_external_owner_exceptions_remain_unchanged():
    import sqlalchemy as sa

    from src.core.database.identity_cutover import reconcile_external_database

    data = {**manifest(), "ignored_external_user_ids": ["user1", "user2"]}
    plan = cutover().validate_manifest(data, [(OLD, NEW)], [ORG])
    with sa.create_engine("sqlite://").begin() as connection:
        connection.execute(sa.text("CREATE TABLE project (id INTEGER PRIMARY KEY, user_id TEXT)"))
        connection.execute(
            sa.text("INSERT INTO project VALUES (1, 'user1'), (2, :old)"), {"old": OLD}
        )
        assert reconcile_external_database(connection, plan, apply=True) == 1
        assert connection.execute(
            sa.text("SELECT user_id FROM project ORDER BY id")
        ).scalars().all() == ["user1", NEW]
        assert reconcile_external_database(connection, plan, apply=False) == 0
    # An external exception never authorizes an unresolved retained SQL UUID.
    with pytest.raises(ValueError, match="Unresolved"):
        plan.resolve("users", "user1")
    data["ignored_external_user_ids"] = [OLD]
    with pytest.raises(ValueError, match="known"):
        cutover().validate_manifest(data, [(OLD, NEW)], [ORG])


def test_external_reconciliation_rolls_back_unique_owner_collision():
    import sqlalchemy as sa

    from src.core.database.identity_cutover import reconcile_external_database

    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE user_mail_credential (id INTEGER PRIMARY KEY, user_id TEXT UNIQUE)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO user_mail_credential VALUES (1, :old), (2, :new)"),
            {"old": OLD, "new": NEW},
        )
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        reconcile_external_database(connection, plan, apply=True)
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT user_id FROM user_mail_credential WHERE id = 1")
            ).scalar()
            == OLD
        )


@pytest.mark.parametrize("shape", ["scalar", "array"])
def test_uuid_identity_mapping_preserves_native_values_and_is_noop(shape):
    from src.core.database.identity_cutover import remap_reference_value

    identity = UUID(NEW)
    value = identity if shape == "scalar" else [identity]
    result = remap_reference_value(value, {NEW: NEW}, shape)
    assert result == value
    assert (result if shape == "scalar" else result[0]) is identity


def test_external_reconciliation_does_not_read_unrelated_document_payloads():
    import sqlalchemy as sa

    from src.core.database.identity_cutover import reconcile_external_database

    plan = cutover().validate_manifest(manifest(), [(OLD, NEW)], [ORG])
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE document (id INTEGER PRIMARY KEY, user_id TEXT, content TEXT)")
        )
        connection.execute(
            sa.text("INSERT INTO document VALUES (1, :owner, :content)"),
            {"owner": OLD, "content": "untouched large document"},
        )
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT") and "FROM document" in statement:
                statements.append(statement)

        sa.event.listen(connection, "before_cursor_execute", capture)
        assert reconcile_external_database(connection, plan, apply=True) == 1
        sa.event.remove(connection, "before_cursor_execute", capture)
        assert statements and all("document.content" not in statement for statement in statements)
        assert (
            connection.execute(sa.text("SELECT content FROM document")).scalar()
            == "untouched large document"
        )
