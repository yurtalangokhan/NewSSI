"""Feature bundles stored as roles on existing Keycloak service clients."""

import asyncio
from typing import Any

from error_contract import BadRequestError

from .keycloak_role_client import (
    BUILTIN,
    PERMISSIONS,
    CoarseRoleRecord,
    KeycloakRoleClient,
    catalog_cache,
    segment,
)


class RoleRepository:
    """Feature roles addressed by Keycloak's immutable role ID.

    A client-role name is unique only within its client, so the ID is the only
    unambiguous handle; names are accepted solely when creating a role.
    """

    def __init__(self):
        self.client = KeycloakRoleClient()

    @staticmethod
    def _record(role, service_client) -> CoarseRoleRecord:
        attributes = role.get("attributes", {})
        return CoarseRoleRecord(
            id=role["id"],
            name=role["name"],
            description=role.get("description"),
            service_client=service_client,
            permissions=tuple(attributes.get(PERMISSIONS, [])),
            is_builtin=attributes.get(BUILTIN) == ["true"],
        )

    async def get_all(self, service_client=None) -> list[CoarseRoleRecord]:
        async def load():
            clients = [
                client
                for client in await self.client.clients()
                if not service_client or client["clientId"] == service_client
            ]
            if not clients:
                return []
            # One round trip per service client, concurrently rather than in series.
            pages = await asyncio.gather(
                *(
                    self.client.pages(f"/clients/{segment(client['id'])}/roles", briefRepresentation=False)
                    for client in clients
                )
            )
            result = [
                self._record(role, client["clientId"])
                for client, roles in zip(clients, pages, strict=True)
                for role in roles
                # Keycloak creates this internal authorization role on service
                # clients; other client roles may legitimately have no attributes.
                if role["name"] != "uma_protection"
            ]
            return sorted(result, key=lambda r: (r.service_client, r.name))

        return list(await catalog_cache.get(("bundles", service_client), load))

    async def get_by_id(self, role_id) -> CoarseRoleRecord | None:
        return next((role for role in await self.get_all() if role.id == role_id), None)

    async def get_by_ids(self, role_ids) -> list[CoarseRoleRecord]:
        wanted = list(dict.fromkeys(role_ids))
        if not wanted:
            # No IDs asked for: skip the Keycloak catalog read entirely.
            return []
        by_id = {role.id: role for role in await self.get_all()}
        return [by_id[role_id] for role_id in wanted if role_id in by_id]

    async def get_permissions_by_ids(self, role_ids) -> dict[str, list[str]]:
        roles = await self.get_by_ids(role_ids)
        expanded = await asyncio.gather(*(self.client.expanded_permissions({"id": role.id}) for role in roles))
        return {role.id: permissions for role, permissions in zip(roles, expanded, strict=True)}

    async def create(self, name, service_client, description=None, permissions=None) -> CoarseRoleRecord:
        client_id = await self.client.client_id(service_client)
        path = f"/clients/{segment(client_id)}/roles"
        await self.client.request(
            "POST",
            path,
            json={
                "name": name,
                "description": description or "",
                "attributes": {PERMISSIONS: permissions or []},
            },
        )
        role = await self.client.request("GET", f"{path}/{segment(name)}")
        return self._record(role, service_client)

    async def update(self, role_id, **updates: Any) -> CoarseRoleRecord | None:
        existing = await self.get_by_id(role_id)
        if not existing:
            return None
        if updates.get("service_client") not in (None, existing.service_client):
            raise BadRequestError()
        path = f"/roles-by-id/{segment(existing.id)}"
        role = await self.client.request("GET", path)
        attributes = dict(role.get("attributes", {}))
        if updates.get("permissions") is not None:
            attributes[PERMISSIONS] = list(updates["permissions"])
        role["attributes"] = attributes
        if updates.get("description") is not None:
            role["description"] = updates["description"]
        await self.client.request("PUT", path, json=role)
        return self._record(role, existing.service_client)

    async def delete(self, role_id) -> bool:
        role = await self.get_by_id(role_id)
        if not role:
            return False
        await self.client.request("DELETE", f"/roles-by-id/{segment(role.id)}")
        return True

    async def exists(self, name, service_client) -> bool:
        return any(role.name == name for role in await self.get_all(service_client))

    async def list_service_clients(self) -> list[str]:
        return sorted(c["clientId"] for c in await self.client.clients())
