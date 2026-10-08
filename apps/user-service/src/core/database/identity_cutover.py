"""Offline, fail-closed validation for the Keycloak identity cutover.

The manifest contains explicit mappings, never inferred email/name matches.
Its inventory is produced by the separate online reconciliation command.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from uuid import UUID

IDENTITY_TABLES = (
    "user_organizations",
    "user_roles",
    "role_hierarchy",
    "role_permissions",
    "organizations",
    "users",
    "composite_roles",
    "roles",
    "permissions",
)
REFERENCES = (
    ("api_keys", "user_id", "users", None),
    ("audit_logs", "user_id", "users", None),
    ("user_settings", "user_id", "users", None),
    ("user_memory", "user_id", "users", None),
    ("resource_permissions", "user_id", "users", None),
    ("resource_permissions", "granted_by", "users", None),
    ("resource_permissions", "organization_id", "organizations", None),
    ("permission_audit_logs", "performed_by", "users", None),
    ("permission_audit_logs", "target_id", "users", "user"),
    ("permission_audit_logs", "target_id", "organizations", "organization"),
)
EXTERNAL_REFERENCES = {
    "agents": {"user_id": "scalar"},
    "persona": {"user_id": "scalar"},
    "document": {"user_id": "scalar"},
    "project": {"user_id": "scalar"},
    "mail_config": {"user_id": "scalar"},
    "mcp_oauth_session": {"user_id": "scalar"},
    "mcp_provider_auth": {"user_id": "scalar"},
    "user_provider_configs": {"user_id": "scalar"},
    "user_mail_credential": {"user_id": "scalar"},
    "agent_instances": {"user_id": "scalar"},
    "agent_groups": {"user_ids": "array", "created_by": "scalar"},
    "agent_flow_versions": {"created_by": "scalar"},
    "thread": {"metadata": "user_id"},
    "langchain_pg_collection": {"cmetadata": "owner_id"},
}


def snapshot_digest(snapshot: dict[str, list[dict]]) -> str:
    """Bind reconciliation evidence to the complete, unchanged source identity rows."""
    canonical = {
        table: sorted(json.dumps(row, sort_keys=True, default=str) for row in rows) for table, rows in snapshot.items()
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def retained_reference_changes(plan, kind, values):
    """Validate present owners and avoid an UPDATE for every imported identity."""
    changes = {}
    for value in values:
        original = str(value)
        target = plan.resolve(kind, value)
        if original != target:
            changes[original] = target
    return changes


def retained_reference_plan(plan, reference, values):
    """Preserve deleted audit targets only; actors and active access stay strict."""
    table, column, kind, discriminator = reference
    historical_targets = {
        ("permission_audit_logs", "target_id", "users", "user"),
        ("permission_audit_logs", "target_id", "organizations", "organization"),
    }
    if reference not in historical_targets:
        return retained_reference_changes(plan, kind, values), []
    current, historical = [], []
    for identity in sorted({str(value) for value in values}):
        if identity in plan.mappings[kind] or identity in plan.inventories[kind]:
            current.append(identity)
            continue
        UUID(identity)
        historical.append(
            {
                "table": table,
                "column": column,
                "target_type": discriminator,
                "identity_kind": kind,
                "target_id": identity,
                "reason": "historical_target_not_in_source_or_keycloak",
            }
        )
    return retained_reference_changes(plan, kind, current), historical


def remap_reference_value(value: Any, mapping: dict[str, str], shape: str) -> Any:
    """Rewrite only declared identity locations; preserve canonical native values."""

    def remap(identity):
        target = mapping.get(str(identity))
        return identity if target is None or target == str(identity) else target

    if value is None:
        return None
    if shape == "scalar":
        return remap(value)
    if shape == "array":
        return [remap(item) for item in value]
    return {**value, shape: remap(value[shape])} if shape in value else value


def reconcile_external_database(connection: Any, plan: "CutoverPlan", *, apply: bool) -> int:
    """Inspect/remap known external fields inside the caller's transaction.

    Unknown identities and uniqueness collisions abort. Shared service accounts
    are preserved; arbitrary payload JSON is never recursively rewritten.
    """
    import sqlalchemy as sa

    inspector = sa.inspect(connection)
    metadata = sa.MetaData()
    changed = 0
    for name in inspector.get_table_names():
        if name not in EXTERNAL_REFERENCES:
            owned = set(IDENTITY_TABLES) | {row[0] for row in REFERENCES}
            if name not in owned:
                columns = {column["name"] for column in inspector.get_columns(name)}
                identity_columns = columns & {
                    "user_id",
                    "owner_id",
                    "organization_id",
                    "user_ids",
                    "created_by",
                }
                if identity_columns:
                    raise ValueError(f"Unregistered identity references in {name}")
            continue
        table = sa.Table(name, metadata, autoload_with=connection)
        if not table.primary_key.columns:
            raise ValueError(f"Cannot safely reconcile table without primary key: {name}")
        if connection.dialect.name == "postgresql":
            quoted = connection.dialect.identifier_preparer.quote(name)
            connection.execute(sa.text(f"LOCK TABLE {quoted} IN ACCESS EXCLUSIVE MODE"))
        selected = {column.name for column in table.primary_key.columns}
        selected.update(EXTERNAL_REFERENCES[name])
        columns = [column for column in table.columns if column.name in selected]
        for row in connection.execute(sa.select(*columns)).mappings():
            updates = {}
            for column, shape in EXTERNAL_REFERENCES[name].items():
                value = row[column]
                if value is None:
                    continue
                identities = (
                    value
                    if shape == "array"
                    else [value]
                    if shape == "scalar"
                    else [value[shape]]
                    if shape in value
                    else []
                )
                for identity in identities:
                    if identity not in (None, "", "internal-service") and (
                        str(identity) not in plan.ignored_external_user_ids
                    ):
                        plan.resolve("users", identity)
                result = remap_reference_value(value, plan.mappings["users"], shape)
                if result != value:
                    updates[column] = result
            if updates:
                changed += 1
                if apply:
                    predicate = sa.and_(*(c == row[c.name] for c in table.primary_key.columns))
                    connection.execute(sa.update(table).where(predicate).values(**updates))
    return changed


@dataclass(frozen=True)
class CutoverPlan:
    mappings: dict[str, dict[str, str]]
    inventories: dict[str, set[str]]
    ignored_external_user_ids: frozenset[str] = frozenset()

    def resolve(self, kind: str, value: object) -> str:
        identity = str(value)
        if identity in self.mappings[kind]:
            return self.mappings[kind][identity]
        if identity in self.inventories[kind]:
            return identity
        raise ValueError(f"Unresolved {kind} reference: {identity}")


def validate_manifest(
    data: dict[str, Any], users: list[tuple[object, object]], organizations: list[object]
) -> CutoverPlan:
    """Validate the complete local identity set against a verified KC inventory."""
    if data.get("version") != 1 or not data.get("realm"):
        raise ValueError("Expected version 1 manifest with a Keycloak realm")
    for field in ("external_references_verified", "keycloak_assignments_verified"):
        if data.get(field) is not True:
            raise ValueError(f"Cutover requires {field}")
    mappings = {}
    inventories = {}
    for kind, rows, inventory_key in (
        ("users", [row[0] for row in users], "keycloak_user_ids"),
        ("organizations", organizations, "keycloak_group_ids"),
    ):
        mapping = data.get(kind, {})
        if not isinstance(mapping, dict):
            raise ValueError(f"Expected explicit {kind} mappings")
        inventory = set(data.get(inventory_key, []))
        for identity in [*mapping, *mapping.values(), *inventory]:
            if str(UUID(identity)) != identity:
                raise ValueError(f"Noncanonical UUID in {kind}")
        if not set(map(str, rows)).issubset(mapping):
            raise ValueError(f"Missing {kind} mappings")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError(f"Cannot merge {kind} identities")
        if not set(mapping.values()).issubset(inventory):
            raise ValueError(f"Unknown Keycloak target in {kind}")
        if any(old in inventory and old != target for old, target in mapping.items()):
            raise ValueError(f"Ambiguous existing Keycloak identity in {kind}")
        # Avoid ambiguous retries and updates when a target is another legacy ID.
        if any(target in mapping and mapping[target] != target for target in mapping.values()):
            raise ValueError(f"Overlapping legacy and Keycloak IDs in {kind}")
        mappings[kind] = mapping
        inventories[kind] = inventory
    for identity, recorded in users:
        if recorded and mappings["users"][str(identity)] != str(recorded):
            raise ValueError(f"Mapping conflicts with recorded Keycloak ID for {identity}")
    ignored = data.get("ignored_external_user_ids", [])
    if not isinstance(ignored, list) or any(not isinstance(v, str) or not v for v in ignored):
        raise ValueError("Expected explicit ignored external user IDs")
    if set(ignored) & (set(mappings["users"]) | inventories["users"]):
        raise ValueError("Cannot ignore a known user identity")
    return CutoverPlan(mappings, inventories, frozenset(ignored))
