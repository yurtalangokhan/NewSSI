"""Assignable permissions from Keycloak feature scopes and client role grants."""

import asyncio
from collections import Counter
from types import SimpleNamespace

from src.core.permissions import list_service_permissions
from src.core.permissions.features import FEATURE_MAP, feature_for

from .coarse_role_repository import RoleRepository
from .keycloak_role_client import KeycloakRoleClient, catalog_cache, segment

_LOCAL_DEFINITIONS = {item["name"]: item for item in list_service_permissions()}
_ENTITY_OWNERS = {
    entity: next(iter(owners))
    for entity in {entity for _, entity in FEATURE_MAP}
    if len(owners := {service for service, item in FEATURE_MAP if item == entity}) == 1
}


class PermissionRepository:
    def __init__(self):
        self.role_repo = RoleRepository()
        self.client = KeycloakRoleClient()

    async def _registered_permissions(self):
        clients = await self.client.clients()

        async def load():
            resources_by_client = await asyncio.gather(*(
                self.client.request(
                    "GET",
                    f"/clients/{segment(client['id'])}/authz/resource-server/resource",
                    params={"max": -1},
                )
                for client in clients
            ))
            return {
                f"{resource['name']}:{scope['name']}": client["clientId"].removesuffix("-client")
                for client, resources in zip(clients, resources_by_client, strict=True)
                for resource in resources
                if resource.get("type") == "agentic:feature"
                for scope in resource.get("scopes", [])
            }

        key = ("permission-scopes", tuple((c["id"], c["clientId"]) for c in clients))
        return await catalog_cache.get(key, load)

    async def get_all(self, service=None, entity=None):
        roles = await self.role_repo.get_all()
        owners = {}
        for role in sorted(roles, key=lambda item: (item.service_client, item.name)):
            for name in role.permissions:
                resource, separator, action = name.partition(":")
                if not separator or not resource or not action or name == "*":
                    continue
                definition = _LOCAL_DEFINITIONS.get(name, {})
                owner = definition.get("service") or _ENTITY_OWNERS.get(
                    resource, role.service_client.removesuffix("-client")
                )
                owners.setdefault(name, owner)
        # A registered scope remains assignable even when no role grants it.
        owners.update(await self._registered_permissions())
        discovered = {}
        for name, owner in owners.items():
            resource, _, action = name.partition(":")
            definition = _LOCAL_DEFINITIONS.get(name, {})
            discovered[name] = SimpleNamespace(
                name=name,
                label=definition.get("label")
                or f"{action} {resource}".replace("_", " ").title(),
                description=definition.get("description"),
                entity=definition.get("entity", resource),
                service=owner,
                action=definition.get("action", action),
                feature=definition.get("feature") or feature_for(owner, resource),
                is_system=definition.get("is_system", False),
            )
        return [
            permission
            for permission in sorted(
                discovered.values(), key=lambda item: (item.service, item.entity, item.name)
            )
            if (not service or permission.service == service)
            and (not entity or permission.entity == entity)
        ]

    async def get_by_name(self, name):
        return next((r for r in await self.get_all() if r.name == name), None)

    async def list_entities(self):
        return [
            {"service": service, "entity": entity}
            for service, entity in sorted({(r.service, r.entity) for r in await self.get_all()})
        ]

    async def count_by_service(self):
        return [
            {"service": service, "count": count}
            for service, count in sorted(Counter(r.service for r in await self.get_all()).items())
        ]
