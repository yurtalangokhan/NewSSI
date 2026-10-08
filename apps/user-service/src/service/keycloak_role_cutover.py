"""Guarded migration of legacy role metadata onto explicitly matched Keycloak roles."""

from src.repository.keycloak_role_client import (
    BUILTIN,
    PERMISSIONS,
    PRIMARY_ROLE,
    DirectKeycloakRoleClient,
    KeycloakRoleClient,
    segment,
)
from src.repository.keycloak_user_update import attribute_update


def _role_client(keycloak):
    if isinstance(keycloak, KeycloakRoleClient) or hasattr(keycloak, "request"):
        return keycloak
    return DirectKeycloakRoleClient(keycloak)


async def reconcile_role_metadata(keycloak, legacy_snapshot, *, apply, mappings=None):
    """Preflight all grants, then fill absent metadata; never alter assignments."""
    client = _role_client(keycloak)
    pending = []
    service_client_ids = set()
    normalized = legacy_snapshot.get("role_permissions", [])
    hierarchy = legacy_snapshot.get("role_hierarchy", [])
    for kind in ("roles", "composite_roles"):
        for row in legacy_snapshot.get(kind, []):
            name = row["name"]
            if kind == "roles":
                clients = await client.request("GET", "/clients", params={"clientId": row["service_client"]})
                matches = [c for c in clients if c["clientId"] == row["service_client"]]
                if len(matches) != 1:
                    raise ValueError(f"Explicit Keycloak client reconciliation required: {name}")
                service_client_ids.add(matches[0]["id"])
                path = f"/clients/{segment(matches[0]['id'])}/roles/{segment(name)}"
            else:
                path = f"/roles/{segment(name)}"
            role = await client.request("GET", path, missing=True)
            if not role:
                raise ValueError(f"Explicit Keycloak role reconciliation required: {name}")
            attributes = dict(role.get("attributes", {}))
            permissions = sorted(
                set(
                    [r["permission_name"] for r in normalized if r["role_name"] == name]
                    if "role_permissions" in legacy_snapshot
                    else row.get("permissions", []) or []
                )
            )
            if PERMISSIONS in attributes and set(attributes[PERMISSIONS]) != set(permissions):
                raise ValueError(f"Permission grant conflict for Keycloak role: {name}")
            if kind == "composite_roles":
                desired = set(
                    [r["child_role"] for r in hierarchy if r["parent_role"] == name]
                    if "role_hierarchy" in legacy_snapshot
                    else row.get("role_ids", []) or []
                )
                children = await client.request("GET", f"/roles-by-id/{segment(role['id'])}/composites")
                actual = {
                    r["name"] for r in children if r.get("clientRole") and r.get("containerId") in service_client_ids
                }
                if desired != actual:
                    raise ValueError(f"Composite grant conflict for Keycloak role: {name}")
            updated = dict(attributes)
            if permissions and PERMISSIONS not in updated:
                updated[PERMISSIONS] = permissions
            if row.get("is_builtin") is True and updated.get(BUILTIN) != ["true"]:
                updated[BUILTIN] = ["true"]
            description = role.get("description") or row.get("description") or ""
            if updated != attributes or description != (role.get("description") or ""):
                pending.append(
                    (
                        "PUT",
                        f"/roles-by-id/{segment(role['id'])}",
                        {**role, "attributes": updated, "description": description or ""},
                    )
                )

    user_map = (mappings or {}).get("users", {})
    primary_by_user = {}
    for assignment in legacy_snapshot.get("user_roles", []):
        if assignment.get("is_primary") is True:
            primary_by_user.setdefault(str(assignment["user_id"]), set()).add(assignment["role_name"])
    for row in legacy_snapshot.get("users", []):
        legacy_id = str(row["id"])
        primary = primary_by_user.get(legacy_id, set())
        if len(primary) > 1:
            raise ValueError(f"Conflicting legacy primary roles: {legacy_id}")
        desired = next(iter(primary), row.get("role"))
        if not desired:
            continue
        user_id = user_map.get(legacy_id)
        if not user_id:
            raise ValueError(f"Explicit Keycloak user reconciliation required: {legacy_id}")
        path = f"/users/{segment(user_id)}"
        user = await client.request("GET", path, missing=True)
        if not user:
            raise ValueError(f"Mapped Keycloak user does not exist: {user_id}")
        effective = await client.request("GET", f"{path}/role-mappings/realm/composite")
        if desired not in {role["name"] for role in effective}:
            raise ValueError(f"Primary role is not effectively assigned in Keycloak: {user_id}")
        attributes = dict(user.get("attributes") or {})
        marker = attributes.get(PRIMARY_ROLE, [])
        if marker and marker != [desired]:
            raise ValueError(f"Primary role metadata conflict for Keycloak user: {user_id}")
        if not marker:
            payload = attribute_update(user, {**attributes, PRIMARY_ROLE: [desired]})
            pending.append(("PUT", path, payload))

    if apply:
        for method, path, payload in pending:
            await client.request(method, path, json=payload)
    return len(pending)


async def ensure_legacy_roles(keycloak, snapshot, apply=False):
    """Create prerequisite roles and add missing edges without replacing grants.

    Dry runs return planned counts and representations; only existing roles have IDs.
    Apply returns verified Keycloak representations, usable by subsequent import phases.
    UserRepresentation.realmRoles takes the returned realm-role dictionary's names.
    """
    client = _role_client(keycloak)
    realm_rows = {row["name"]: row for row in snapshot.get("composite_roles", [])}
    for row in snapshot.get("users", []):
        if row.get("role"):
            realm_rows.setdefault(row["role"], {"name": row["role"]})
    for row in snapshot.get("user_roles", []):
        realm_rows.setdefault(row["role_name"], {"name": row["role_name"]})
    feature_rows = {}
    for row in snapshot.get("roles", []):
        if row["name"] in feature_rows:
            raise ValueError(f"Ambiguous legacy feature role: {row['name']}")
        feature_rows[row["name"]] = row
    permissions = {}
    for row in snapshot.get("role_permissions", []):
        permissions.setdefault(row["role_name"], set()).add(row["permission_name"])
    hierarchy = snapshot.get("role_hierarchy")
    if hierarchy is None:
        hierarchy = [
            {"parent_role": row["name"], "child_role": child}
            for row in realm_rows.values()
            for child in row.get("role_ids", []) or []
        ]
    edges = set()
    for edge in hierarchy:
        parent, child = edge["parent_role"], edge["child_role"]
        if parent not in realm_rows or child not in feature_rows:
            raise ValueError(f"Unknown legacy composite edge: {parent} -> {child}")
        edges.add((parent, child))

    service_ids = {}
    for service in sorted({row["service_client"] for row in feature_rows.values()}):
        clients = await client.request("GET", "/clients", params={"clientId": service})
        matches = [item for item in clients if item["clientId"] == service]
        if len(matches) != 1:
            raise ValueError(f"Explicit Keycloak service-client reconciliation required: {service}")
        service_ids[service] = matches[0]["id"]
    catalogs = {"realm_roles": {}, "client_roles": {}}
    creates = []
    for kind, rows in (("realm_roles", realm_rows), ("client_roles", feature_rows)):
        for name, row in sorted(rows.items()):
            path = (
                "/roles" if kind == "realm_roles" else f"/clients/{segment(service_ids[row['service_client']])}/roles"
            )
            existing = await client.request("GET", f"{path}/{segment(name)}", missing=True)
            if existing:
                catalogs[kind][name] = existing
                continue
            values = (
                sorted(permissions.get(name, set()))
                if "role_permissions" in snapshot
                else row.get("permissions", []) or []
            )
            attributes = {PERMISSIONS: values}
            if row.get("is_builtin") is True:
                attributes[BUILTIN] = ["true"]
            payload = {
                "name": name,
                "description": row.get("description") or "",
                "attributes": attributes,
            }
            catalogs[kind][name] = payload
            creates.append((kind, name, path, payload))
    missing_edges = []
    existing_children = {}
    for parent, child in sorted(edges):
        parent_role = catalogs["realm_roles"][parent]
        if parent not in existing_children:
            existing_children[parent] = (
                await client.request("GET", f"/roles-by-id/{segment(parent_role['id'])}/composites")
                if parent_role.get("id")
                else []
            )
        child_id = catalogs["client_roles"][child].get("id")
        if child_id is None or child_id not in {r["id"] for r in existing_children[parent]}:
            missing_edges.append((parent, child))
    if apply:
        for kind, name, path, payload in creates:
            await client.request("POST", path, json=payload)
            created = await client.request("GET", f"{path}/{segment(name)}")
            if not created or not created.get("id"):
                raise ValueError(f"Cannot verify created Keycloak role: {name}")
            catalogs[kind][name] = created
        by_parent = {}
        for parent, child in missing_edges:
            by_parent.setdefault(parent, []).append(catalogs["client_roles"][child])
        for parent, children in by_parent.items():
            role_id = catalogs["realm_roles"][parent]["id"]
            path = f"/roles-by-id/{segment(role_id)}/composites"
            await client.request("POST", path, json=children)
            actual = {role["id"] for role in await client.request("GET", path)}
            if not {role["id"] for role in children}.issubset(actual):
                raise ValueError(f"Cannot verify Keycloak composite links: {parent}")
    return {**catalogs, "roles_created": len(creates), "hierarchy_edges_added": len(missing_edges)}
