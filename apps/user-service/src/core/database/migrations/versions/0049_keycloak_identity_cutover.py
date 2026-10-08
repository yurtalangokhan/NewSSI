"""Archive local identity and retain only validated Keycloak references.

Run the reconciliation command with all writers stopped before this revision.
Pass its manifest with ``alembic -x identity_manifest=/absolute/path upgrade head``.
No network calls occur inside this transaction.
"""

import json
from pathlib import Path

from alembic import context, op
import sqlalchemy as sa

from src.core.database.identity_cutover import (
    IDENTITY_TABLES,
    REFERENCES,
    retained_reference_plan,
    snapshot_digest,
    validate_manifest,
)

revision = "0049"
down_revision = "0048_flow_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = context.get_x_argument(as_dictionary=True).get("identity_manifest")
    if not path or context.is_offline_mode():
        raise ValueError("0049 requires an online database and verified identity_manifest")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    from config_manager import env

    if data.get("realm") != env.KEYCLOAK_REALM:
        raise ValueError("Cutover manifest belongs to a different Keycloak realm")
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        raise ValueError("Identity cutover requires PostgreSQL transactional DDL")
    tables = sa.inspect(connection).get_table_names()
    required = set(IDENTITY_TABLES) | {reference[0] for reference in REFERENCES}
    if not required.issubset(tables):
        raise ValueError(f"Missing cutover tables: {sorted(required - set(tables))}")
    quote = connection.dialect.identifier_preparer.quote
    names = ", ".join(quote(name) for name in sorted(required))
    connection.execute(sa.text(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE"))
    snapshot = {
        table: [dict(row) for row in connection.execute(sa.text(f"SELECT * FROM {quote(table)}")).mappings()]
        for table in IDENTITY_TABLES
    }
    if data.get("source_digest") != snapshot_digest(snapshot):
        raise ValueError("Identity source changed since reconciliation; generate a fresh manifest")
    users = list(connection.execute(sa.text("SELECT id, keycloak_id FROM users")))
    organizations = list(connection.execute(sa.text("SELECT id FROM organizations")).scalars())
    plan = validate_manifest(data, users, organizations)
    # Inspect every retained reference before the first mutation, including old audit actors.
    retained_changes = {}
    historical_audit_targets = []
    for table, column, kind, discriminator in REFERENCES:
        where = f"{quote(column)} IS NOT NULL"
        if discriminator:
            where += " AND target_type = :target_type"
        values = connection.execute(
            sa.text(f"SELECT DISTINCT {quote(column)} FROM {quote(table)} WHERE {where}"),
            {"target_type": discriminator},
        ).scalars()
        reference = (table, column, kind, discriminator)
        changes, historical = retained_reference_plan(plan, reference, values)
        retained_changes[reference] = changes
        historical_audit_targets.extend(historical)
    inspector = sa.inspect(connection)
    retained_fks = []
    for table in tables:
        if table in IDENTITY_TABLES:
            continue
        for foreign_key in inspector.get_foreign_keys(table):
            if foreign_key["referred_table"] in IDENTITY_TABLES:
                expected = {(t, c) for t, c, _, _ in REFERENCES}
                if any((table, c) not in expected for c in foreign_key["constrained_columns"]):
                    raise ValueError(f"Unregistered identity foreign key in {table}")
                retained_fks.append((table, foreign_key["name"]))
    # Fail if the archive already exists. Never overwrite a previous recovery snapshot.
    connection.execute(sa.text("CREATE SCHEMA identity_cutover_archive"))
    for table in IDENTITY_TABLES:
        connection.execute(sa.text(f"CREATE TABLE identity_cutover_archive.{quote(table)} AS TABLE {quote(table)}"))
    connection.execute(sa.text("CREATE TABLE identity_cutover_archive.manifest (document JSONB NOT NULL)"))
    connection.execute(
        sa.text("INSERT INTO identity_cutover_archive.manifest VALUES (CAST(:document AS JSONB))"),
        {"document": json.dumps({**data, "historical_audit_targets": historical_audit_targets})},
    )
    for table, constraint in retained_fks:
        op.drop_constraint(constraint, table, type_="foreignkey")
    for table, column, kind, discriminator in REFERENCES:
        for old, new in retained_changes[(table, column, kind, discriminator)].items():
            where = f"{quote(column)} = CAST(:old AS UUID)"
            if discriminator:
                where += " AND target_type = :target_type"
            connection.execute(
                sa.text(f"UPDATE {quote(table)} SET {quote(column)} = CAST(:new AS UUID) WHERE {where}"),
                {"old": old, "new": new, "target_type": discriminator},
            )
    # No CASCADE: an unregistered dependency aborts and rolls back the entire cutover.
    for table in IDENTITY_TABLES:
        op.drop_table(table)


def downgrade() -> None:
    raise RuntimeError("Restore the coordinated pre-cutover backup; automatic rollback is unsafe")
