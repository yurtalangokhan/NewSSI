"""Grant the Existing Connectors UI permission to the Knowledge Manager bundle.

The page requires ``datasource:view``. Like ``embedding:view``, this UI-only
permission is held in the Keycloak client role's ``agentic.permissions``
attribute; no gateway route checks a ``view`` scope. Run without ``--apply``
to inspect the change, then use ``--apply`` to write it.
"""

import argparse
import asyncio

from config_manager import env

from src.repository.keycloak_role_client import (
    PERMISSIONS,
    DirectKeycloakRoleClient,
    segment,
)

ROLE_NAME = "knowledge-manager"
VIEW_PERMISSION = "datasource:view"


async def ensure_datasource_view(
    client, *, apply: bool, service_client_name: str | None = None
) -> bool:
    """Add the grant once, preserving every unrelated role attribute."""
    client_name = service_client_name or env.KEYCLOAK_RAG_SERVICE_CLIENT_ID
    clients = await client.request("GET", "/clients", params={"clientId": client_name})
    matches = [item for item in clients if item.get("clientId") == client_name]
    if len(matches) != 1:
        raise ValueError(f"Expected one Keycloak service client: {client_name}")
    role = await client.request(
        "GET",
        f"/clients/{segment(matches[0]['id'])}/roles/{segment(ROLE_NAME)}",
        missing=True,
    )
    if not role or role.get("name") != ROLE_NAME:
        raise ValueError(f"Keycloak client role does not exist: {client_name}/{ROLE_NAME}")
    attributes = dict(role.get("attributes") or {})
    permissions = set(attributes.get(PERMISSIONS) or [])
    if "datasource:read" not in permissions:
        raise ValueError(f"{client_name}/{ROLE_NAME} lacks datasource:read")
    if VIEW_PERMISSION in permissions:
        return False
    attributes[PERMISSIONS] = sorted(permissions | {VIEW_PERMISSION})
    if apply:
        await client.request(
            "PUT",
            f"/roles-by-id/{segment(role['id'])}",
            json={**role, "attributes": attributes},
        )
    return True


async def _main(apply: bool) -> None:
    from src.service.keycloak_service import get_keycloak_service

    client = DirectKeycloakRoleClient(get_keycloak_service())
    changed = await ensure_datasource_view(client, apply=apply)
    if changed:
        print("Granted datasource:view to knowledge-manager" if apply
              else "Would grant datasource:view to knowledge-manager")
    else:
        print("knowledge-manager already grants datasource:view")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Keycloak")
    args = parser.parse_args()
    asyncio.run(_main(args.apply))


if __name__ == "__main__":
    main()
