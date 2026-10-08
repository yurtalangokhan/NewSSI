"""Platform roles are authoritative Keycloak realm roles."""

import asyncio
from collections.abc import Iterable

from error_contract import BadRequestError

from .coarse_role_repository import RoleRepository
from .keycloak_role_client import (
    BUILTIN,
    PERMISSIONS,
    CompositeRoleRecord,
    KeycloakRoleClient,
    manageable,
    segment,
)


class CompositeRoleRepository:
    """Platform roles addressed by Keycloak's immutable role ID.

    Names are resolved only for what Keycloak itself expresses by name: realm
    role claims in access tokens and uniqueness on create.
    """

    def __init__(self):
        self.client = KeycloakRoleClient()

    def _feature_roles(self) -> RoleRepository:
        repo = RoleRepository()
        repo.client = self.client
        return repo

    async def _record(self, role) -> CompositeRoleRecord:
        children = []
        if role.get("composite"):
            children = await self.client.request("GET", f"/roles-by-id/{segment(role['id'])}/composites")
        if children:
            service_ids = {client["id"] for client in await self.client.clients()}
            children = [
                child for child in children if child.get("clientRole") and child.get("containerId") in service_ids
            ]
        attributes = role.get("attributes", {})
        permissions = attributes.get(PERMISSIONS, [])
        if role["name"] == "system-admin":
            permissions = ["*"]
        return CompositeRoleRecord(
            id=role["id"],
            name=role["name"],
            description=role.get("description"),
            permissions=tuple(permissions),
            bundle_ids=tuple(child["id"] for child in children),
            bundle_names=tuple(child["name"] for child in children),
            is_builtin=attributes.get(BUILTIN) == ["true"],
        )

    @staticmethod
    def _is_platform_role(role) -> bool:
        return bool(role) and not role.get("clientRole") and manageable(role["name"])

    async def _representation(self, role_id):
        role = await self.client.request("GET", f"/roles-by-id/{segment(role_id)}", missing=True)
        return role if self._is_platform_role(role) else None

    async def get_by_id(self, role_id) -> CompositeRoleRecord | None:
        role = await self._representation(role_id)
        return await self._record(role) if role else None

    async def get_by_name(self, name) -> CompositeRoleRecord | None:
        if not manageable(name):
            return None
        role = await self.client.request("GET", f"/roles/{segment(name)}", missing=True)
        return await self._record(role) if self._is_platform_role(role) else None

    async def get_all(self) -> list[CompositeRoleRecord]:
        roles = await self.client.pages("/roles", briefRepresentation=False)
        # _record fans out to Keycloak per composite role; run those concurrently.
        return list(
            await asyncio.gather(
                *(self._record(role) for role in sorted(roles, key=lambda r: r["name"]) if self._is_platform_role(role))
            )
        )

    async def get_by_names(self, names: Iterable[str]) -> list[CompositeRoleRecord]:
        roles = [await self.get_by_name(name) for name in dict.fromkeys(names)]
        return [role for role in roles if role]

    async def get_by_ids(self, role_ids: Iterable[str]) -> list[CompositeRoleRecord]:
        roles = [await self.get_by_id(role_id) for role_id in dict.fromkeys(role_ids)]
        return [role for role in roles if role]

    async def get_access_by_names(self, names: Iterable[str]) -> dict[str, list[str]]:
        """Effective permissions per token role name, composites expanded by Keycloak."""
        roles = await self.get_by_names(names)
        expanded = await asyncio.gather(*(self.client.expanded_permissions({"id": role.id}) for role in roles))
        return {role.name: permissions for role, permissions in zip(roles, expanded, strict=True)}

    async def get_default_admin_role(self) -> CompositeRoleRecord | None:
        return await self.get_by_name("system-admin")

    async def create(
        self,
        name: str,
        description: str | None = None,
        permissions: Iterable[str] = (),
        bundle_ids: Iterable[str] = (),
        is_builtin: bool = False,
    ) -> CompositeRoleRecord:
        if not manageable(name):
            raise BadRequestError()
        bundle_ids = list(bundle_ids)
        if bundle_ids:
            await self._validated_bundles(bundle_ids)
        await self.client.request(
            "POST",
            "/roles",
            json={
                "name": name,
                "description": description or "",
                "attributes": {
                    PERMISSIONS: list(permissions),
                    **({BUILTIN: ["true"]} if is_builtin else {}),
                },
            },
        )
        created = await self.client.request("GET", f"/roles/{segment(name)}")
        if bundle_ids:
            return await self.update(created["id"], bundle_ids=bundle_ids)
        return await self._record(created)

    async def _validated_bundles(self, bundle_ids: list[str]):
        bundles = await self._feature_roles().get_by_ids(bundle_ids)
        if len(bundles) != len(set(bundle_ids)):
            raise BadRequestError()
        return bundles

    async def update(
        self,
        role_id: str,
        *,
        description: str | None = None,
        permissions: Iterable[str] | None = None,
        bundle_ids: Iterable[str] | None = None,
        is_builtin: bool | None = None,
    ) -> CompositeRoleRecord | None:
        role = await self._representation(role_id)
        if not role:
            return None
        bundles = await self._validated_bundles(list(bundle_ids)) if bundle_ids is not None else None
        attributes = dict(role.get("attributes", {}))
        if permissions is not None:
            attributes[PERMISSIONS] = list(permissions)
        if is_builtin is True:
            attributes[BUILTIN] = ["true"]
        elif is_builtin is False:
            attributes.pop(BUILTIN, None)
        role["attributes"] = attributes
        if description is not None:
            role["description"] = description
        path = f"/roles-by-id/{segment(role['id'])}"
        await self.client.request("PUT", path, json=role)
        if bundles is not None:
            await self._replace_bundles(role["id"], bundles)
        return await self.get_by_id(role["id"])

    async def _replace_bundles(self, role_id, bundles) -> None:
        path = f"/roles-by-id/{segment(role_id)}/composites"
        current = await self.client.request("GET", path)
        # Preserve unrelated realm and infrastructure-client composites.
        service_ids = {c["id"] for c in await self.client.clients()}
        desired = {bundle.id for bundle in bundles}
        current_ids = {child["id"] for child in current}
        remove = [
            child
            for child in current
            if child.get("clientRole") and child.get("containerId") in service_ids and child["id"] not in desired
        ]
        add = [{"id": b.id, "name": b.name} for b in bundles if b.id not in current_ids]
        if remove:
            await self.client.request("DELETE", path, json=remove)
        if add:
            await self.client.request("POST", path, json=add)

    async def delete(self, role_id: str) -> bool:
        role = await self._representation(role_id)
        if not role:
            return False
        await self.client.request("DELETE", f"/roles-by-id/{segment(role['id'])}")
        return True

    async def exists(self, name: str) -> bool:
        return await self.get_by_name(name) is not None
