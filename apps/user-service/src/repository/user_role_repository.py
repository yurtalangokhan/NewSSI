"""Authoritative direct and inherited Keycloak realm-role mappings."""

import asyncio
from contextlib import AsyncExitStack
import uuid

from error_contract import BadRequestError, NotFoundError

from .keycloak_role_client import (
    PRIMARY_ROLE,
    KeycloakRoleClient,
    manageable,
    primary_role_name,
    segment,
)
from .keycloak_user_update import attribute_update


class UserRoleRepository:
    def __init__(self):
        self.client = KeycloakRoleClient()

    def _path(self, user_id):
        return f"/users/{segment(user_id)}"

    async def get_primary_roles(self, user_ids):
        from src.service.keycloak_service import get_keycloak_service

        identities = list(dict.fromkeys(user_ids))
        if not identities:
            return {}

        async def primary(user_id):
            path = self._path(user_id)
            user = await self.client.request("GET", path, missing=True)
            if user is None:
                return ""
            effective = await self.client.request("GET", f"{path}/role-mappings/realm/composite")
            return primary_role_name(
                [role["name"] for role in effective if manageable(role["name"])],
                user.get("attributes", {}).get(PRIMARY_ROLE, []),
            )

        result = {}
        keycloak = get_keycloak_service()
        async with AsyncExitStack() as stack:
            scope = getattr(type(keycloak), "admin_request_scope", None)
            if scope is not None:
                await stack.enter_async_context(scope(keycloak))
            for first in range(0, len(identities), 8):
                wave = identities[first : first + 8]
                outcomes = await asyncio.gather(*(primary(user_id) for user_id in wave), return_exceptions=True)
                for user_id, role in zip(wave, outcomes, strict=True):
                    if isinstance(role, BaseException):
                        raise role
                    if role:
                        result[user_id] = role
        return result

    async def list_user_roles(self, user_id):
        path = self._path(user_id)
        user = await self.client.request("GET", path, missing=True)
        if user is None:
            return []
        effective = await self.client.request("GET", f"{path}/role-mappings/realm/composite")
        direct = await self.client.request("GET", f"{path}/role-mappings/realm")
        primary = primary_role_name(
            [r["name"] for r in effective if manageable(r["name"])],
            user.get("attributes", {}).get(PRIMARY_ROLE, []),
        )
        ids = {r["id"] for r in direct}
        return sorted(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "is_primary": r["name"] == primary,
                    "inherited": r["id"] not in ids,
                }
                for r in effective
                if manageable(r["name"])
            ],
            key=lambda r: (not r["is_primary"], r["name"]),
        )

    async def effective_client_permissions(self, user_id):
        permissions = set()
        for client in await self.client.clients():
            roles = await self.client.request(
                "GET",
                f"{self._path(user_id)}/role-mappings/clients/{segment(client['id'])}/composite",
            )
            for role in roles:
                permissions.update(await self.client.expanded_permissions(role))
        return sorted(permissions)

    async def list_user_ids_by_role(self, role_name):
        from .user_repository import UserRepository

        directory = UserRepository()
        async with AsyncExitStack() as stack:
            scope = getattr(type(directory.keycloak), "admin_request_scope", None)
            if scope is not None:
                await stack.enter_async_context(scope(directory.keycloak))
            # Revocation needs fresh membership for this role, not a full realm
            # scan (or a wait behind a concurrent role-distribution rebuild).
            index = await directory._build_role_index(role_name=role_name)
        return [uuid.UUID(identity) for identity, names in index.items() if role_name in names]

    async def _roles(self, names):
        roles = []
        for name in dict.fromkeys(names):
            if not manageable(name):
                raise BadRequestError()
            role = await self.client.request("GET", f"/roles/{segment(name)}", missing=True)
            if not role:
                raise NotFoundError()
            roles.append(role)
        return roles

    @staticmethod
    def _invalidate_role_index():
        from .user_repository import UserRepository

        UserRepository.invalidate_role_index()

    async def _primary(self, user_id, role_name):
        path = self._path(user_id)
        user = await self.client.request("GET", path)
        attributes = dict(user.get("attributes", {}))
        if role_name:
            attributes[PRIMARY_ROLE] = [role_name]
        else:
            attributes.pop(PRIMARY_ROLE, None)
        await self.client.request("PUT", path, json=attribute_update(user, attributes))

    async def assign_roles(self, user_id, role_names, primary_role=None):
        roles = await self._roles(role_names)
        if (
            primary_role
            and primary_role not in role_names
            and not any(r["name"] == primary_role for r in await self.list_user_roles(user_id))
        ):
            raise BadRequestError()
        if roles:
            await self.client.request("POST", f"{self._path(user_id)}/role-mappings/realm", json=roles)
        if primary_role is not None:
            await self._primary(user_id, primary_role)
        self._invalidate_role_index()

    async def replace_roles(self, user_id, role_names, primary_role=None):
        roles = await self._roles(role_names)
        if primary_role is not None and primary_role not in role_names:
            raise BadRequestError()
        path = f"{self._path(user_id)}/role-mappings/realm"
        current = await self.client.request("GET", path)
        stale = [r for r in current if manageable(r["name"]) and r["name"] not in role_names]
        if stale:
            await self.client.request("DELETE", path, json=stale)
        if roles:
            await self.client.request("POST", path, json=roles)
        await self._primary(user_id, primary_role)
        self._invalidate_role_index()
        return len(stale)

    async def remove_role(self, user_id, role_name):
        path = f"{self._path(user_id)}/role-mappings/realm"
        direct = await self.client.request("GET", path)
        matches = [r for r in direct if r["name"] == role_name and manageable(role_name)]
        if not matches:
            return False
        await self.client.request("DELETE", path, json=matches)
        user = await self.client.request("GET", self._path(user_id))
        if role_name in user.get("attributes", {}).get(PRIMARY_ROLE, []):
            await self._primary(user_id, None)
        self._invalidate_role_index()
        return True

    async def set_primary_role(self, user_id, role_name):
        if not any(r["name"] == role_name for r in await self.list_user_roles(user_id)):
            return False
        await self._primary(user_id, role_name)
        self._invalidate_role_index()
        return True
