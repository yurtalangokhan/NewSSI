"""Give enterprise-admin every managed grant except System Settings.

The realm role inherits service-owned admin bundles. Four UI-only page views
belong to the agent-service admin bundle as role attributes; gateway routes do
not use them as scopes. Run without ``--apply`` to inspect, then apply.
"""

import argparse
import asyncio

from config_manager import env

from src.repository.keycloak_role_client import (
    PERMISSIONS,
    DirectKeycloakRoleClient,
    segment,
)

REALM_ROLE = "enterprise-admin"
ADMIN_BUNDLES = {
    "agent-service-client": "agent-workspace-admin",
    "rag-service-client": "knowledge-admin",
    "tools-service-client": "tooling-admin",
    "user-service-client": "access-admin",
}
MISSING_PAGE_VIEWS = frozenset(
    {"mail_config:view", "mcp_tool:view", "provider:view", "web_search:view"}
)


def _grants(role: dict) -> set[str]:
    return set((role.get("attributes") or {}).get(PERMISSIONS) or [])


def _refuse_system_settings(grants: set[str]) -> None:
    if any(grant.startswith("system.settings:") for grant in grants):
        raise ValueError("Enterprise admin must not inherit System Settings permissions")


async def reconcile_enterprise_admin(
    client, *, apply: bool, client_names: tuple[str, ...] | None = None
) -> dict[str, list[str] | dict[str, list[str]]]:
    """Preflight all grants, then make only missing Keycloak writes."""
    names = client_names or (
        env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID,
        env.KEYCLOAK_RAG_SERVICE_CLIENT_ID,
        env.KEYCLOAK_TOOLS_SERVICE_CLIENT_ID,
        env.KEYCLOAK_USER_SERVICE_CLIENT_ID,
    )
    required_bundles = dict(zip(names, ADMIN_BUNDLES.values(), strict=True))
    agent_name = names[0]
    roles: dict[tuple[str, str], dict] = {}
    catalog_grants: set[str] = set()
    scopes_by_client: dict[str, set[str]] = {}
    for name in names:
        client_id = await client.client_id(name)
        resources = await client.request(
            "GET",
            f"/clients/{segment(client_id)}/authz/resource-server/resource",
            params={"max": -1},
        )
        scopes_by_client[name] = {
            f"{resource['name']}:{scope['name']}"
            for resource in resources
            if resource.get("type") == "agentic:feature"
            for scope in resource.get("scopes", [])
            if not resource["name"].startswith("system.settings")
        }
        for summary in await client.pages(f"/clients/{segment(client_id)}/roles"):
            full = await client.request("GET", f"/roles-by-id/{segment(summary['id'])}")
            roles[name, full["name"]] = full
            catalog_grants.update(_grants(full))

    for name, bundle in required_bundles.items():
        if (name, bundle) not in roles:
            raise ValueError(f"Missing Keycloak admin bundle: {name}/{bundle}")
        _refuse_system_settings(_grants(roles[name, bundle]))

    agent_admin = roles[agent_name, required_bundles[agent_name]]
    view_additions = sorted(MISSING_PAGE_VIEWS - _grants(agent_admin))
    scope_additions = {
        name: sorted(scopes - _grants(roles[name, bundle]))
        for name, bundle in required_bundles.items()
        if (scopes := scopes_by_client[name]) - _grants(roles[name, bundle])
    }
    realm_role = await client.request("GET", f"/roles/{segment(REALM_ROLE)}")
    if realm_role.get("clientRole"):
        raise ValueError("enterprise-admin must be a realm role")
    children = await client.request(
        "GET", f"/roles-by-id/{segment(realm_role['id'])}/composites"
    )
    child_ids = {child["id"] for child in children}
    required_roles = [roles[name, bundle] for name, bundle in required_bundles.items()]
    additions = [role for role in required_roles if role["id"] not in child_ids]

    effective = _grants(realm_role)
    for child in children:
        full = await client.request("GET", f"/roles-by-id/{segment(child['id'])}")
        effective.update(_grants(full))
    for role in additions:
        effective.update(_grants(role))
    effective.update(MISSING_PAGE_VIEWS)
    for missing in scope_additions.values():
        effective.update(missing)
    _refuse_system_settings(effective)
    target = {grant for grant in catalog_grants if not grant.startswith("system.settings:")}
    target.update(MISSING_PAGE_VIEWS)
    for scopes in scopes_by_client.values():
        target.update(scopes)
    uncovered = target - effective
    if uncovered:
        raise ValueError(f"Admin bundles do not cover managed grants: {', '.join(sorted(uncovered))}")

    if apply:
        for name, bundle in required_bundles.items():
            role = roles[name, bundle]
            extra = set(scope_additions.get(name, []))
            if name == agent_name:
                extra.update(view_additions)
            if not extra:
                continue
            attributes = dict(role.get("attributes") or {})
            attributes[PERMISSIONS] = sorted(_grants(role) | extra)
            await client.request(
                "PUT",
                f"/roles-by-id/{segment(role['id'])}",
                json={**role, "attributes": attributes},
            )
    if apply and additions:
        await client.request(
            "POST",
            f"/roles-by-id/{segment(realm_role['id'])}/composites",
            json=[{"id": role["id"], "name": role["name"]} for role in additions],
        )
    return {
        "role_additions": sorted(role["name"] for role in additions),
        "view_additions": view_additions,
        "scope_additions": scope_additions,
    }


async def _main(apply: bool) -> None:
    from src.service.keycloak_service import get_keycloak_service

    plan = await reconcile_enterprise_admin(
        DirectKeycloakRoleClient(get_keycloak_service()), apply=apply
    )
    action = "Applied" if apply else "Would apply"
    print(f"{action} role additions: {', '.join(plan['role_additions']) or 'none'}")
    print(f"{action} page views: {', '.join(plan['view_additions']) or 'none'}")
    for name, scopes in plan["scope_additions"].items():
        print(f"{action} {name} scopes: {', '.join(scopes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Keycloak")
    asyncio.run(_main(parser.parse_args().apply))


if __name__ == "__main__":
    main()
