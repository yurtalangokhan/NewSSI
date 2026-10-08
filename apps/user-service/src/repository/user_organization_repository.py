"""Keycloak group memberships with application metadata in user attributes."""

from datetime import UTC, datetime
import json
import uuid

from error_contract import NotFoundError

from .keycloak_group_client import KeycloakGroupClient
from .keycloak_user_update import attribute_update
from .organization_repository import OrganizationRepository

MEMBERSHIPS = "agenticai.memberships"
PRIMARY = "agenticai.primary_organization"


class UserOrganizationRepository:
    def __init__(self, keycloak=None):
        self.client = KeycloakGroupClient(keycloak)
        self.organizations = OrganizationRepository(self.client.keycloak)

    @staticmethod
    def _metadata(user):
        return json.loads((user.get("attributes") or {}).get(MEMBERSHIPS, ["{}"])[0])

    async def _save(self, user, metadata, primary=None):
        attrs = dict(user.get("attributes") or {})
        attrs[MEMBERSHIPS] = [json.dumps(metadata)]
        if primary is not None:
            attrs[PRIMARY] = [str(primary)] if primary else []
        response = await self.client.request("PUT", f"/users/{user['id']}", json=attribute_update(user, attrs))
        if response is None:
            raise NotFoundError()

    @staticmethod
    def _to_dict(user, org, metadata, active):
        user_id, org_id = uuid.UUID(user["id"]), org["id"]
        primary = (user.get("attributes") or {}).get(PRIMARY) or [None]
        return {
            "id": uuid.UUID(metadata["id"])
            if metadata.get("id")
            else uuid.uuid5(uuid.NAMESPACE_URL, f"keycloak-membership:{user_id}:{org_id}"),
            "user_id": user_id,
            "organization_id": org_id,
            "is_primary": active and primary[0] == str(org_id),
            "is_active": active,
            "joined_at": metadata.get("joined_at"),
            "assigned_by": uuid.UUID(metadata["assigned_by"]) if metadata.get("assigned_by") else None,
            "user": {
                "id": user_id,
                "username": user.get("username"),
                "email": user.get("email"),
                "first_name": user.get("firstName"),
                "last_name": user.get("lastName"),
                "role": None,
            },
            "organization": {key: org[key] for key in ("id", "name", "code", "level")},
        }

    async def _memberships(self, user, include_inactive=False, organizations=None):
        metadata = self._metadata(user)
        groups = await self.client.pages(f"/users/{user['id']}/groups")
        active_ids = {g["id"] for g in groups}
        ids = active_ids | (set(metadata) if include_inactive else set())
        organizations = (
            organizations if organizations is not None else await self.organizations._get_by_ids(sorted(ids))
        )
        result = []
        for org in organizations:
            group_id = str(org["id"])
            if group_id not in ids:
                continue
            active = group_id in active_ids
            if include_inactive or (active and org["is_active"]):
                result.append(self._to_dict(user, org, metadata.get(group_id, {}), active))
        return sorted(result, key=lambda m: (m["is_primary"], m["joined_at"] or ""), reverse=True)

    async def get_user_organizations(self, user_id, include_inactive=False):
        async with self.organizations._request_scope():
            user = await self.client.get(f"/users/{user_id}")
            return await self._memberships(user, include_inactive) if user else []

    async def get_by_user_and_org(self, user_id, organization_id):
        return next(
            (
                m
                for m in await self.get_user_organizations(user_id, True)
                if str(m["organization_id"]) == str(organization_id)
            ),
            None,
        )

    async def get_by_id(self, user_org_id):
        organizations = await self.organizations._all()
        for user in await self.client.pages("/users"):
            for member in await self._memberships(user, True, organizations):
                if str(member["id"]) == str(user_org_id):
                    return member
        return None

    async def create(self, user_id, organization_id, is_primary=False, assigned_by=None):
        user = await self.client.get(f"/users/{user_id}")
        if not user or not await self.organizations.get_by_id(organization_id):
            raise NotFoundError()
        metadata = self._metadata(user)
        metadata[str(organization_id)] = {
            "joined_at": datetime.now(UTC).isoformat(),
            "is_active": True,
            "assigned_by": str(assigned_by) if assigned_by else None,
            **metadata.get(str(organization_id), {}),
        }
        response = await self.client.request("PUT", f"/users/{user_id}/groups/{organization_id}")
        if response is None:
            raise NotFoundError()
        await self._save(user, metadata, organization_id if is_primary else None)
        return await self.get_by_user_and_org(user_id, organization_id)

    async def update(self, user_org_id, **updates):
        member = await self.get_by_id(user_org_id)
        return await self._update_member(member, **updates)

    async def update_by_user_and_org(self, user_id, organization_id, **updates):
        """Update a known relationship without searching the user directory."""
        async with self.organizations._request_scope():
            member = await self.get_by_user_and_org(user_id, organization_id)
            return await self._update_member(member, **updates)

    async def _update_member(self, member, **updates):
        if not member:
            return None
        user_id, org_id = member["user_id"], member["organization_id"]
        user = await self.client.get(f"/users/{user_id}")
        metadata = self._metadata(user)
        entry = metadata.setdefault(str(org_id), {"id": str(member["id"])})
        for key in ("is_active", "assigned_by", "joined_at"):
            if key in updates:
                value = updates[key]
                entry[key] = str(value) if isinstance(value, uuid.UUID) else value
        active = updates.get("is_active", member["is_active"])
        if "is_active" in updates:
            await self.client.request("PUT" if active else "DELETE", f"/users/{user_id}/groups/{org_id}")
        primary = None
        if updates.get("is_primary") and active:
            primary = org_id
        elif member["is_primary"] and (not active or updates.get("is_primary") is False):
            primary = ""
        await self._save(user, metadata, primary)
        return await self.get_by_user_and_org(user_id, org_id)

    async def delete(self, user_id, organization_id):
        member = await self.get_by_user_and_org(user_id, organization_id)
        if not member:
            return False
        user = await self.client.get(f"/users/{user_id}")
        await self.client.request("DELETE", f"/users/{user_id}/groups/{organization_id}")
        metadata = self._metadata(user)
        metadata.pop(str(organization_id), None)
        await self._save(user, metadata, "" if member["is_primary"] else None)
        return True

    async def delete_and_cleanup_orphan_permissions(self, user_id, organization_id):
        from .keycloak_resource_authorization import project_resource_permission_mutation
        from .resource_permission_repository import ResourcePermissionRepository

        deleted = await self.delete(user_id, organization_id)
        if not deleted or await self.get_user_organizations(user_id):
            return deleted, 0
        permissions = ResourcePermissionRepository()
        count = await project_resource_permission_mutation(lambda: permissions.delete_user_permissions(user_id))
        return True, count

    async def set_primary(self, user_id, organization_id):
        member = await self.get_by_user_and_org(user_id, organization_id)
        if not member or not member["is_active"]:
            return None
        user = await self.client.get(f"/users/{user_id}")
        await self._save(user, self._metadata(user), organization_id)
        return await self.get_by_user_and_org(user_id, organization_id)

    async def get_primary_organization(self, user_id):
        return next((m for m in await self.get_user_organizations(user_id) if m["is_primary"]), None)

    async def get_organization_users(self, organization_id, include_inactive=False):
        async with self.organizations._request_scope():
            org = await self.organizations.get_by_id(organization_id)
            if not org or (not include_inactive and not org["is_active"]):
                return []
            users = await self.client.pages(f"/groups/{organization_id}/members")
            active_ids = {user["id"] for user in users}
            group_id = str(org["id"])
            result = []

            def append_member(user):
                metadata = self._metadata(user)
                active = user["id"] in active_ids
                if active or group_id in metadata:
                    result.append(self._to_dict(user, org, metadata.get(group_id, {}), active))

            if include_inactive:
                # Detached memberships exist only in user metadata, so this optional
                # view still needs profiles, but never a group lookup per user.
                from .user_repository import UserRepository

                async for user in UserRepository(self.client.keycloak)._pages("/users"):
                    append_member(user)
            else:
                for user in users:
                    append_member(user)
            return sorted(result, key=lambda m: m["joined_at"] or "")

    async def get_all_active_organization_users(self):
        organizations = await self.organizations._all()
        result = []
        for user in await self.client.pages("/users"):
            result.extend(await self._memberships(user, organizations=organizations))
        return sorted(result, key=lambda m: (str(m["organization_id"]), m["joined_at"] or ""))

    async def get_active_unit_manager_organizations(self, user_id):
        from .user_role_repository import UserRoleRepository

        assignments = await UserRoleRepository().list_user_roles(user_id)
        if not any("".join(c for c in r["name"].lower() if c.isalnum()) == "unitmanager" for r in assignments):
            return []
        return await self.get_user_organizations(user_id)

    async def count_organization_users(self, organization_id):
        return len(await self.get_organization_users(organization_id))
