"""Grant personal-memory CRUD to the Keycloak end-user self-service bundle.

Only user-service route scopes are granted here. The RAG memory index retains
its separate `memory:search` and `memory:write` scopes. Preview without
``--apply``; after applying, reproject the gateway authorization policies.
"""

import argparse
import asyncio

from config_manager import env

from src.repository.keycloak_role_client import (
    PERMISSIONS,
    DirectKeycloakRoleClient,
    segment,
)

ROLE_NAME = "account-self-service"
MEMORY_GRANTS = frozenset(
    {"memory:create", "memory:delete", "memory:read", "memory:update"}
)


async def grant_enduser_memory(
    client, *, apply: bool, service_client_name: str | None = None
) -> list[str]:
    """Add only missing user-service Memory grants to an inherited client role."""
    client_name = service_client_name or env.KEYCLOAK_USER_SERVICE_CLIENT_ID
    clients = await client.request("GET", "/clients", params={"clientId": client_name})
    matches = [item for item in clients if item.get("clientId") == client_name]
    if len(matches) != 1:
        raise ValueError(f"Expected one Keycloak service client: {client_name}")
    client_id = matches[0]["id"]
    role = await client.request(
        "GET", f"/clients/{segment(client_id)}/roles/{segment(ROLE_NAME)}", missing=True
    )
    if not role or role.get("name") != ROLE_NAME or not role.get("clientRole"):
        raise ValueError(f"Keycloak client role does not exist: {client_name}/{ROLE_NAME}")

    enduser = await client.request("GET", "/roles/enduser")
    children = await client.request(
        "GET", f"/roles-by-id/{segment(enduser['id'])}/composites"
    )
    if role["id"] not in {child["id"] for child in children}:
        raise ValueError(f"enduser does not inherit {client_name}/{ROLE_NAME}")

    resources = await client.request(
        "GET",
        f"/clients/{segment(client_id)}/authz/resource-server/resource",
        params={"max": -1},
    )
    registered = {
        f"memory:{scope['name']}"
        for resource in resources
        if resource.get("type") == "agentic:feature" and resource.get("name") == "memory"
        for scope in resource.get("scopes", [])
    }
    if not registered.issuperset(MEMORY_GRANTS):
        raise ValueError(f"{client_name} lacks required Memory gateway scopes")

    attributes = dict(role.get("attributes") or {})
    existing = set(attributes.get(PERMISSIONS) or [])
    missing = sorted(MEMORY_GRANTS - existing)
    if apply and missing:
        attributes[PERMISSIONS] = sorted(existing | MEMORY_GRANTS)
        await client.request(
            "PUT",
            f"/roles-by-id/{segment(role['id'])}",
            json={**role, "attributes": attributes},
        )
    return missing


async def _main(apply: bool) -> None:
    from src.service.keycloak_service import get_keycloak_service

    missing = await grant_enduser_memory(
        DirectKeycloakRoleClient(get_keycloak_service()), apply=apply
    )
    action = "Granted" if apply else "Would grant"
    print(f"{action} enduser Memory permissions: {', '.join(missing) or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Keycloak")
    asyncio.run(_main(parser.parse_args().apply))


if __name__ == "__main__":
    main()
