"""Reconcile application metadata without changing Keycloak identities or assignments."""

from datetime import date, datetime
import json
from uuid import UUID

from src.repository.keycloak_group_client import KeycloakGroupClient
from src.repository.keycloak_user_update import attribute_update
from src.repository.organization_repository import PREFIX
from src.repository.user_organization_repository import MEMBERSHIPS, PRIMARY


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported metadata value: {type(value).__name__}")


def _merge_attribute(attributes, key, values):
    existing = attributes.get(key)
    if existing and existing != values:
        # JSON object key ordering does not constitute a metadata conflict.
        try:
            equivalent = len(existing) == len(values) == 1 and (json.loads(existing[0]) == json.loads(values[0]))
        except (ValueError, TypeError):
            equivalent = False
        if not equivalent:
            raise ValueError(f"Keycloak metadata conflict for {key}")
    else:
        attributes[key] = values


async def reconcile_group_metadata(keycloak, legacy_snapshot, mappings, *, apply=False) -> int:
    """Plan all missing metadata updates, fail conflicts, and optionally apply.

    Group names, parent links, user profiles, memberships, and role mappings remain
    authoritative in Keycloak. Active legacy memberships must already exist; the
    operator must resolve discrepancies before identity tables can be dropped.
    """
    client = KeycloakGroupClient(keycloak)
    planned = []
    user_updates = {}
    current_memberships = {}

    def mapped(kind, value):
        result = mappings.get(kind, {}).get(str(value))
        if result is None:
            raise ValueError(f"Unresolved {kind} identity {value}")
        return str(result)

    for row in legacy_snapshot.get("organizations", []):
        org_id = mapped("organizations", row["id"])
        group = await client.get(f"/groups/{org_id}")
        if group is None:
            raise ValueError(f"Keycloak organization {org_id} no longer exists")
        original = group.get("attributes") or {}
        attrs = dict(original)
        for key in (
            "code",
            "description",
            "order_index",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
            "metadata",
        ):
            source = "metadata_json" if key == "metadata" else key
            value = row.get(source)
            if value is None:
                continue
            if key == "created_by":
                value = mapped("users", value)
            _merge_attribute(attrs, PREFIX + key, [json.dumps(value, default=_json_value)])
        if attrs != original:
            planned.append((f"/groups/{org_id}", {"name": group["name"], "attributes": attrs}))

    for row in legacy_snapshot.get("users", []):
        user_id = mapped("users", row["id"])
        user = await client.get(f"/users/{user_id}")
        if user is None:
            raise ValueError(f"Keycloak user {user_id} no longer exists")
        original = user.get("attributes") or {}
        attrs = dict(original)
        for key in ("team_name", "invited", "password_configured", "is_external_keycloak_user"):
            value = row.get(key)
            if value is not None:
                value = str(value).lower() if isinstance(value, bool) else str(value)
                _merge_attribute(attrs, f"agentic.{key}", [value])
        user_updates[user_id] = (user, original, attrs)

    for row in legacy_snapshot.get("user_organizations", []):
        user_id = mapped("users", row["user_id"])
        org_id = mapped("organizations", row["organization_id"])
        if user_id not in user_updates:
            raise ValueError(f"Membership user {user_id} is missing from the snapshot")
        if user_id not in current_memberships:
            current_memberships[user_id] = {g["id"] for g in await client.pages(f"/users/{user_id}/groups")}
        active = org_id in current_memberships[user_id]
        if row.get("is_active", True) != active:
            raise ValueError(f"Keycloak membership conflict for {user_id}/{org_id}")
        _, _, attrs = user_updates[user_id]
        metadata = json.loads((attrs.get(MEMBERSHIPS) or ["{}"])[0])
        existing = metadata.get(org_id, {})
        entry = dict(existing)
        for key in ("id", "joined_at", "assigned_by", "is_active"):
            value = row.get(key)
            if value is None:
                continue
            if key == "assigned_by":
                value = mapped("users", value)
            value = json.loads(json.dumps(value, default=_json_value))
            if key in entry and entry[key] != value:
                raise ValueError(f"Keycloak metadata conflict for membership {org_id}/{key}")
            entry[key] = value
        metadata[org_id] = entry
        attrs[MEMBERSHIPS] = [json.dumps(metadata)]
        if row.get("is_primary"):
            if not active:
                raise ValueError(f"Primary membership {org_id} is inactive")
            _merge_attribute(attrs, PRIMARY, [org_id])

    for user_id, (user, original, attrs) in user_updates.items():
        if attrs != original:
            planned.append((f"/users/{user_id}", attribute_update(user, attrs)))
    if apply:
        for path, payload in planned:
            if await client.request("PUT", path, json=payload) is None:
                raise ValueError(f"Keycloak identity disappeared during reconciliation: {path}")
    return len(planned)
