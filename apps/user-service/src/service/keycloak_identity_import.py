"""Resumable Keycloak partial imports with explicit legacy identity provenance."""

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime
import json
from uuid import UUID

from src.repository.keycloak_group_inventory import read_group_inventory

LEGACY_ID = "agentic.legacy_identity_id"


def _json(value):
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, UUID):
            return str(item)
        raise TypeError(type(item).__name__)

    return json.dumps(value, default=encode)


def build_group_forest(rows, user_mapping=None):
    """Create a complete import tree; names and paths are checked before writes."""
    user_mapping = user_mapping or {}
    nodes, paths, parents = {}, {}, {}
    for row in rows:
        identity = str(row["id"])
        name = row["name"]
        if not name or "/" in name:
            raise ValueError(f"Organization name requires explicit path reconciliation: {identity}")
        attrs = {LEGACY_ID: [identity]}
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
            value = row.get("metadata_json" if key == "metadata" else key)
            if value is not None:
                if key == "created_by":
                    value = user_mapping.get(str(value))
                    if value is None:
                        raise ValueError("Organization creator must be mapped before group import")
                attrs["agenticai.organization." + key] = [_json(value)]
        nodes[identity] = {"name": name, "attributes": attrs, "subGroups": []}
        parents[identity] = str(row["parent_id"]) if row.get("parent_id") else None

    visiting = set()

    def path(identity):
        if identity in paths:
            return paths[identity]
        if identity in visiting:
            raise ValueError("Organization hierarchy contains a cycle")
        if identity not in nodes:
            raise ValueError("Organization parent is missing")
        visiting.add(identity)
        parent = parents[identity]
        result = (path(parent) if parent else "") + "/" + nodes[identity]["name"]
        paths[identity] = result
        visiting.remove(identity)
        return result

    forest = []
    for identity, node in nodes.items():
        node["path"] = path(identity)
        parent = parents[identity]
        (nodes[parent]["subGroups"] if parent else forest).append(node)
    if len(set(paths.values())) != len(paths):
        raise ValueError("Duplicate organization paths")
    return forest, paths


def match_users(rows, profiles):
    """Reuse recorded subjects or importer-marked accounts; reject name/email collisions."""
    by_id = {p["id"]: p for p in profiles}
    by_name = {p["username"].casefold(): p for p in profiles}
    by_email = {p["email"].casefold(): p for p in profiles if p.get("email")}
    mapping, names, emails = {}, set(), set()
    for row in rows:
        identity = str(row["id"])
        name, email = row["username"].casefold(), (row.get("email") or "").casefold()
        if name in names or (email and email in emails):
            raise ValueError("Duplicate legacy username or email")
        names.add(name)
        if email:
            emails.add(email)
        recorded = row.get("keycloak_id")
        if recorded:
            if str(recorded) not in by_id:
                raise ValueError(f"Recorded Keycloak subject is missing: {identity}")
            mapping[identity] = str(recorded)
            continue
        existing = by_name.get(name) or by_email.get(email)
        if existing:
            if (existing.get("attributes") or {}).get(LEGACY_ID) != [identity]:
                raise ValueError(f"Keycloak username/email collision: {identity}")
            if existing["username"].casefold() != name:
                raise ValueError(f"Keycloak username/email collision: {identity}")
            mapping[identity] = existing["id"]
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Legacy users would merge into one Keycloak subject")
    return mapping


def build_user_payloads(snapshot, user_mapping, group_mapping, group_paths):
    assignments, memberships = defaultdict(list), defaultdict(list)
    for row in snapshot.get("user_roles", []):
        assignments[str(row["user_id"])].append(row)
    for row in snapshot.get("user_organizations", []):
        memberships[str(row["user_id"])].append(row)
    payloads = []
    for row in snapshot["users"]:
        identity = str(row["id"])
        if identity in user_mapping:
            continue
        if row.get("hashed_password"):
            raise ValueError(f"Legacy password needs a supported credential migration: {identity}")
        roles = assignments[identity]
        primary = {r["role_name"] for r in roles if r.get("is_primary")}
        if len(primary) > 1:
            raise ValueError(f"Conflicting primary roles: {identity}")
        primary_role = next(iter(primary), row.get("role"))
        names = sorted({r["role_name"] for r in roles} or {primary_role or "enduser"})
        if primary_role and primary_role not in names:
            raise ValueError(f"Primary role is not assigned: {identity}")
        attrs = {LEGACY_ID: [identity], "agentic.primary_role": [primary_role or names[0]]}
        for key in ("team_name", "invited", "password_configured", "is_external_keycloak_user"):
            value = row.get(key)
            if value is not None:
                attrs["agentic." + key] = [str(value).lower() if isinstance(value, bool) else str(value)]
        metadata, groups = {}, []
        for membership in memberships[identity]:
            legacy_group = str(membership["organization_id"])
            group = group_mapping[legacy_group]
            entry = {}
            for key in ("id", "joined_at", "assigned_by", "is_active"):
                value = membership.get(key)
                if value is not None:
                    if key == "assigned_by":
                        value = user_mapping.get(str(value))
                        if value is None:
                            raise ValueError("Membership assigner must be mapped before user import")
                    entry[key] = value
            metadata[group] = entry
            if membership.get("is_active", True):
                groups.append(group_paths[legacy_group])
            if membership.get("is_primary"):
                if not membership.get("is_active", True):
                    raise ValueError("Primary membership is inactive")
                if "agenticai.primary_organization" in attrs:
                    raise ValueError("Multiple primary organizations")
                attrs["agenticai.primary_organization"] = [group]
        if metadata:
            attrs["agenticai.memberships"] = [_json(metadata)]
        payload = {
            "username": row["username"],
            "enabled": row.get("is_active", True),
            "emailVerified": row.get("is_verified", False),
            "attributes": attrs,
            "realmRoles": names,
            "groups": groups,
        }
        if row.get("created_at") is not None:
            created = row["created_at"]
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            payload["createdTimestamp"] = int(created.timestamp() * 1000)
        for source, target in (
            ("email", "email"),
            ("first_name", "firstName"),
            ("last_name", "lastName"),
        ):
            if row.get(source) is not None:
                payload[target] = row[source]
        payloads.append(payload)
    return payloads


async def user_profiles(keycloak, page_size=1000):
    profiles, seen = [], set()

    async def fetch(first):
        response = await keycloak._keycloak_request(
            "GET",
            "/users",
            params={
                "first": first,
                "max": page_size,
                "briefRepresentation": "false",
            },
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list) or any(
            not isinstance(profile, dict) or not isinstance(profile.get("id"), str) or not profile["id"]
            for profile in page
        ):
            raise ValueError("Invalid Keycloak user inventory page")
        return page

    pages = [await fetch(0)]
    first = page_size
    while True:
        for page in pages:
            for profile in page:
                if profile["id"] in seen:
                    raise ValueError("Keycloak user inventory repeated IDs")
                seen.add(profile["id"])
            profiles.extend(page)
            if len(page) < page_size:
                return profiles
        pages = None
        page = None
        results = await asyncio.gather(
            *(fetch(offset) for offset in range(first, first + 8 * page_size, page_size)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        pages = results
        results = None
        result = None
        first += 8 * page_size


async def group_profiles(keycloak):
    groups = await read_group_inventory(keycloak)
    by_path = {group["path"]: group for group in groups.values()}
    if len(by_path) != len(groups):
        raise ValueError("Keycloak group inventory repeated paths")
    return by_path


async def import_missing_identities(keycloak, snapshot, *, batch_size=500, concurrency=4, progress=None):
    """Import missing records; every restart resolves live provenance before writing.

    Existing accounts and their assignments are untouched. No passwords are generated.
    The returned mapping is read back from Keycloak, never inferred from source IDs.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    if not 1 <= concurrency <= 8:
        raise ValueError("concurrency must be between 1 and 8")
    profiles = await user_profiles(keycloak)
    mapping = match_users(snapshot["users"], profiles)
    forest, paths = build_group_forest(snapshot["organizations"], mapping)
    existing = await group_profiles(keycloak)
    for identity, path in paths.items():
        if path in existing and existing[path].get("attributes", {}).get(LEGACY_ID) != [identity]:
            raise ValueError(f"Keycloak organization path collision: {identity}")
    missing_roots = [root for root in forest if root["path"] not in existing]
    # A partial import skips an existing root and cannot repair missing descendants.
    for root in forest:
        if root["path"] in existing and any(
            p not in existing for p in paths.values() if p.startswith(root["path"] + "/")
        ):
            raise ValueError("Existing imported group tree is incomplete")
    for root in missing_roots:
        response = await keycloak._keycloak_request(
            "POST",
            "/partialImport",
            json={
                "ifResourceExists": "FAIL",
                "groups": [root],
            },
        )
        response.raise_for_status()
    if missing_roots:
        existing = await group_profiles(keycloak)
    group_mapping = {}
    for identity, path in paths.items():
        group = existing.get(path)
        if not group or group.get("attributes", {}).get(LEGACY_ID) != [identity]:
            raise ValueError(f"Imported organization failed read-back: {identity}")
        group_mapping[identity] = group["id"]
    payloads = build_user_payloads(snapshot, mapping, group_mapping, paths)
    if progress:
        progress("groups", len(group_mapping), len(group_mapping))
    batches = iter(range(0, len(payloads), batch_size))
    completed = 0
    failure = None

    async def worker():
        nonlocal completed, failure
        while failure is None:
            first = next(batches, None)
            if first is None:
                return
            batch = payloads[first : first + batch_size]
            try:
                response = await keycloak._keycloak_request(
                    "POST",
                    "/partialImport",
                    json={"ifResourceExists": "FAIL", "users": batch},
                )
                response.raise_for_status()
            except Exception as exc:
                # Stop scheduling new work. Let other in-flight requests finish so
                # restart can inspect provenance; never retry an uncertain write.
                if failure is None:
                    failure = exc
                return
            completed += len(batch)
            if progress:
                progress("users", completed, len(payloads))

    worker_count = min(concurrency, (len(payloads) + batch_size - 1) // batch_size)
    async with asyncio.TaskGroup() as tasks:
        for _ in range(worker_count):
            tasks.create_task(worker())
    if failure is not None:
        raise failure
    profiles = await user_profiles(keycloak)
    mapping = match_users(snapshot["users"], profiles)
    if len(mapping) != len(snapshot["users"]):
        raise ValueError("Imported user inventory is incomplete")
    return {"users": mapping, "organizations": group_mapping}
