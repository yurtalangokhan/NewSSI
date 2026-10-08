"""Add legacy grants to pre-existing Keycloak identities without replacing assignments."""

from collections import defaultdict

from src.repository.keycloak_role_client import segment


async def import_existing_assignments(keycloak, snapshot, mappings, realm_roles, *, apply=False):
    """Import only users with recorded Keycloak subjects; retry skips effective grants.

    `realm_roles` is ensure_legacy_roles(..., apply=True)["realm_roles"]. Reads finish
    before writes begin. Subsequent reconciliation verifies all resulting assignments.
    """

    async def request(method, path, **kwargs):
        if hasattr(keycloak, "request"):
            return await keycloak.request(method, path, **kwargs)
        response = await keycloak._keycloak_request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    existing = {str(row["id"]): row for row in snapshot.get("users", []) if row.get("keycloak_id")}
    roles_by_user, groups_by_user = defaultdict(set), defaultdict(set)
    for row in snapshot.get("user_roles", []):
        identity = str(row["user_id"])
        if identity in existing:
            roles_by_user[identity].add(row["role_name"])
    for row in snapshot.get("user_organizations", []):
        identity = str(row["user_id"])
        if identity in existing and row.get("is_active", True):
            group_id = mappings.get("organizations", {}).get(str(row["organization_id"]))
            if not group_id:
                raise ValueError(f"Missing organization mapping for existing user: {identity}")
            groups_by_user[identity].add(str(group_id))
    for identity, row in existing.items():
        target = mappings.get("users", {}).get(identity)
        if not target or str(target) != str(row["keycloak_id"]):
            raise ValueError(f"Existing Keycloak subject mapping changed: {identity}")
        if not roles_by_user[identity] and row.get("role"):
            roles_by_user[identity].add(row["role"])
        for name in roles_by_user[identity]:
            role = realm_roles.get(name)
            if not role or not role.get("id") or role.get("clientRole"):
                raise ValueError(f"Missing verified Keycloak realm role: {name}")

    pending_groups, pending_roles = [], []
    for identity, row in existing.items():
        path = f"/users/{segment(row['keycloak_id'])}"
        groups = set()
        first = 0
        while True:
            page = await request("GET", f"{path}/groups", params={"first": first, "max": 1000})
            if any(group["id"] in groups for group in page):
                raise ValueError("Keycloak membership pagination repeated IDs")
            groups.update(group["id"] for group in page)
            if len(page) < 1000:
                break
            first += len(page)
        effective = await request("GET", f"{path}/role-mappings/realm/composite")
        names = {role["name"] for role in effective}
        pending_groups.extend(f"{path}/groups/{segment(group)}" for group in sorted(groups_by_user[identity] - groups))
        additions = [realm_roles[name] for name in sorted(roles_by_user[identity] - names)]
        if additions:
            pending_roles.append((f"{path}/role-mappings/realm", additions))
    if apply:
        for path in pending_groups:
            await request("PUT", path)
        for path, roles in pending_roles:
            await request("POST", path, json=roles)
    return {
        "memberships_added": len(pending_groups),
        "roles_added": sum(len(roles) for _, roles in pending_roles),
    }
