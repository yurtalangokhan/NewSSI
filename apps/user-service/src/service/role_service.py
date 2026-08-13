import logging
from typing import Any

from i18n import t

from src.repository import CompositeRoleRepository, PermissionRepository

from .coarse_role_service import get_role_service
from .keycloak_service import get_keycloak_service

logger = logging.getLogger(__name__)

# Maps realm role → per-service coarse client roles to assign.
# These coarse roles appear in the JWT resource_access claim (small, fixed-size).
# Fine-grained permission resolution happens in user-service DB.
COARSE_SERVICE_ROLES: dict[str, dict[str, list[str]]] = {
    "user-service": {
        "system-admin": ["user-admin"],
        "enterprise-admin": ["user-manager"],
        "enduser": ["enduser"],
    },
    "agent-service": {
        "system-admin": ["agent-admin"],
        "enterprise-admin": ["agent-manager"],
        "enduser": ["agent-enduser"],
    },
    "rag-service": {
        "system-admin": ["rag-admin"],
        "enterprise-admin": ["rag-manager"],
        "enduser": ["rag-enduser"],
    },
    "tools-service": {
        "system-admin": ["tool-admin"],
        "enterprise-admin": ["tool-user"],
        "enduser": ["tool-user"],
    },
}

# All known coarse role names — used during cleanup to avoid deleting them.
ALL_COARSE_ROLE_NAMES: set[str] = {
    name
    for svc_roles in COARSE_SERVICE_ROLES.values()
    for names in svc_roles.values()
    for name in names
}


def _coarse_roles_for_db_role(role_name: str) -> dict[str, list[str]]:
    """Return the coarse role mapping for a given DB role name.
    Unknown roles get enduser-level access by default.
    """
    for _svc_client, realm_map in COARSE_SERVICE_ROLES.items():
        if role_name in realm_map:
            result: dict[str, list[str]] = {}
            for svc, mapping in COARSE_SERVICE_ROLES.items():
                result[svc] = mapping.get(role_name, mapping.get("enduser", []))
            return result
    # Fallback: enduser level for unknown roles
    return _coarse_roles_for_db_role("enduser")


class CompositeRoleService:
    def __init__(self):
        self.role_repo = CompositeRoleRepository()
        self.permission_repo = PermissionRepository()
        self.keycloak = get_keycloak_service()

    async def _users_with_role(self, role_name: str):
        from src.repository import UserRepository

        return await UserRepository().list_by_role(role_name)

    async def _invalidate_sessions_for_role_users(self, role_name: str) -> int:
        if not self.keycloak.is_enabled():
            return 0

        invalidated = 0
        for user in await self._users_with_role(role_name):
            if not getattr(user, "keycloak_id", None):
                continue
            logged_out = await self.keycloak.logout_user_sessions(user.keycloak_id)
            if not logged_out:
                raise ValueError(
                    t("role.session_invalidation_failed_for_user", email=user.email)
                )
            invalidated += 1
        return invalidated

    # ----------------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------------

    async def list_roles(self) -> list[dict[str, Any]]:
        roles = await self.role_repo.get_all()
        return [
            {
                "name": r.name,
                "description": r.description,
                "permissions": r.permissions,
                "role_ids": r.role_ids or [],
                "is_builtin": r.is_builtin,
                "is_admin": r.is_admin,
            }
            for r in roles
        ]

    async def get_role(self, name: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_name(name)
        if not role:
            return None
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "role_ids": role.role_ids or [],
            "is_builtin": role.is_builtin,
            "is_admin": role.is_admin,
        }

    async def create_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
        is_builtin: bool = False,
    ) -> dict[str, Any]:
        if await self.role_repo.exists(name):
            raise ValueError(t("role.already_exists", name=name))
        role = await self.role_repo.create(
            name=name,
            description=description,
            permissions=permissions or [],
            role_ids=role_ids or [],
            is_builtin=is_builtin,
        )
        if self.keycloak.is_enabled():
            await self._sync_role_to_keycloak(role)
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "role_ids": role.role_ids or [],
            "is_builtin": role.is_builtin,
            "is_admin": role.is_admin,
        }

    async def update_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        updates: dict[str, Any] = {}
        if description is not None:
            updates["description"] = description
        if permissions is not None:
            updates["permissions"] = permissions
        if role_ids is not None:
            updates["role_ids"] = role_ids
        role = await self.role_repo.update(name, **updates)
        if not role:
            return None
        if self.keycloak.is_enabled():
            await self._sync_role_to_keycloak(role)
        if permissions is not None or role_ids is not None:
            await self._invalidate_sessions_for_role_users(name)
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "role_ids": role.role_ids or [],
            "is_builtin": role.is_builtin,
            "is_admin": role.is_admin,
        }

    async def delete_role(self, name: str) -> bool:
        role = await self.role_repo.get_by_name(name)
        if role and role.is_builtin:
            raise ValueError(t("role.cannot_delete_builtin", name=name))
        if role and await self._users_with_role(name):
            raise ValueError(t("role.cannot_delete_in_use", name=name))
        deleted = await self.role_repo.delete(name)
        if deleted and self.keycloak.is_enabled():
            await self.keycloak.delete_realm_role(name)
        return deleted

    async def get_role_permissions(self, name: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_name(name)
        if not role:
            return None
        # Resolve permissions: direct perms + aggregated from roles
        effective_perms = await self._resolve_effective_permissions(role)
        return {
            "name": role.name,
            "permissions": effective_perms,
            "role_ids": role.role_ids or [],
        }

    async def _resolve_effective_permissions(self, role) -> list[str]:
        """Resolve effective permissions for a role.
        Merges direct permissions with aggregated permissions from roles.
        Returns ["*"] if any source grants wildcard access.
        """
        perms = role.permissions or []
        rids = role.role_ids or []

        # Wildcard in direct perms → everything
        if perms == ["*"]:
            return ["*"]

        # No role IDs → use direct perms only
        if not rids:
            return list(perms) if perms else []

        # Aggregate from roles
        cr_svc = get_role_service()
        coarse_perms = await cr_svc.get_aggregated_permissions(rids)

        # Check for wildcard in role perms
        if "*" in coarse_perms:
            return ["*"]

        # Merge direct + role, deduplicate
        merged = set(perms or [])
        merged.update(coarse_perms)
        return sorted(merged)

    async def set_role_permissions(
        self, name: str, permissions: list[str]
    ) -> dict[str, Any] | None:
        all_perms = await self.permission_repo.get_all()
        valid_names = {p.name for p in all_perms}
        invalid = [p for p in permissions if p not in valid_names and p != "*"]
        if invalid:
            raise ValueError(t("role.invalid_permissions", permissions=invalid))

        role = await self.role_repo.update(name, permissions=permissions)
        if not role:
            return None
        if self.keycloak.is_enabled():
            await self._sync_role_to_keycloak(role)
        await self._invalidate_sessions_for_role_users(name)
        effective = await self._resolve_effective_permissions(role)
        return {
            "name": role.name,
            "permissions": effective,
            "role_ids": role.role_ids or [],
        }

    async def get_role_role_ids(self, name: str) -> dict[str, Any] | None:
        """Get the list of role IDs assigned to a composite role."""
        role = await self.role_repo.get_by_name(name)
        if not role:
            return None
        return {
            "name": role.name,
            "role_ids": role.role_ids or [],
        }

    async def set_role_role_ids(self, name: str, role_ids: list[str]) -> dict[str, Any] | None:
        """Set the list of role IDs assigned to a composite role."""
        # Validate roles exist
        cr_svc = get_role_service()
        existing = await cr_svc.repo.get_by_names(role_ids)
        existing_names = {r.name for r in existing}
        invalid = [n for n in role_ids if n not in existing_names]
        if invalid:
            raise ValueError(t("role.invalid_role_ids", roles=invalid))

        role = await self.role_repo.update(name, role_ids=role_ids)
        if not role:
            return None
        if self.keycloak.is_enabled():
            await self._sync_role_to_keycloak(role)
        await self._invalidate_sessions_for_role_users(name)
        effective = await self._resolve_effective_permissions(role)
        return {
            "name": role.name,
            "role_ids": role.role_ids or [],
            "effective_permissions": effective,
        }

    # ----------------------------------------------------------------
    # Full sync: DB → Keycloak
    # ----------------------------------------------------------------

    async def sync_to_keycloak(self) -> dict[str, Any]:
        if not self.keycloak.is_enabled():
            return {"status": "skipped", "reason": "Keycloak not enabled"}

        stats: dict[str, Any] = {
            "service_clients_ensured": 0,
            "coarse_roles_created": 0,
            "permission_roles_cleaned": 0,
            "protocol_mappers_removed": 0,
            "realm_roles_created": 0,
            "role_composites_set": 0,
            "user_realm_roles_synced": 0,
            "errors": [],
        }

        all_roles = await self.role_repo.get_all()

        # Step 1: Ensure all backend service clients exist
        for svc_client in COARSE_SERVICE_ROLES:
            try:
                if await self.keycloak.ensure_client(svc_client):
                    stats["service_clients_ensured"] += 1
            except Exception as e:
                stats["errors"].append(f"Failed to ensure client '{svc_client}': {e}")

        # Step 2: Clean up permission-level client roles, create coarse roles
        for svc_client in COARSE_SERVICE_ROLES:
            try:
                stats["permission_roles_cleaned"] += await self._cleanup_permission_roles(
                    svc_client
                )
                stats["coarse_roles_created"] += await self._ensure_coarse_roles(svc_client)
            except Exception as e:
                stats["errors"].append(f"Failed to sync roles for '{svc_client}': {e}")

        # Step 3: Sync realm roles with coarse client role composites
        for role in all_roles:
            try:
                realm_role = await self.keycloak.get_realm_role(role.name)
                if not realm_role:
                    await self.keycloak.create_realm_role(
                        role.name,
                        role.description or f"{role.name} composite role",
                    )
                    stats["realm_roles_created"] += 1

                await self._set_role_coarse_composites(role.name)
                stats["role_composites_set"] += 1
            except Exception as e:
                stats["errors"].append(f"Failed to sync realm role '{role.name}': {e}")

        # Step 4: Remove protocol mappers that put permissions in JWT
        try:
            mapper_results = await self.keycloak.remove_permissions_protocol_mappers()
            stats["protocol_mappers_removed"] = sum(1 for v in mapper_results.values() if v)
        except Exception as e:
            stats["errors"].append(f"Failed to remove protocol mappers: {e}")

        # Step 5: Sync user realm role assignments
        from src.repository import UserRepository

        users = await UserRepository().get_all()
        for user in users:
            if not user.keycloak_id:
                continue
            try:
                await self.keycloak.set_realm_role(user.keycloak_id, str(user.role))
                stats["user_realm_roles_synced"] += 1
            except Exception as e:
                stats["errors"].append(f"Failed to sync user '{user.email}' role: {e}")

        return stats

    # ----------------------------------------------------------------
    # Single-role sync (called on create/update)
    # ----------------------------------------------------------------

    async def _sync_role_to_keycloak(self, role) -> None:
        # Ensure backend service clients exist
        for svc_client in COARSE_SERVICE_ROLES:
            await self.keycloak.ensure_client(svc_client)

        # Ensure realm role exists
        if not await self.keycloak.get_realm_role(role.name):
            await self.keycloak.create_realm_role(
                role.name,
                role.description or f"{role.name} composite role",
            )

        # Ensure roles exist and set composites
        # Uses DB-stored role_ids if available, falls back to hardcoded mapping
        role_id_names = list(role.role_ids or [])
        if not role_id_names:
            # Fallback: use hardcoded COARSE_SERVICE_ROLES mapping
            for svc_client in COARSE_SERVICE_ROLES:
                names = _coarse_roles_for_db_role(role.name).get(svc_client, [])
                role_id_names.extend(names)

        for name in role_id_names:
            # Find which service client this role belongs to
            found_svc = None
            for svc_client, realm_map in COARSE_SERVICE_ROLES.items():
                for svc_names in realm_map.values():
                    if name in svc_names:
                        found_svc = svc_client
                        break
                if found_svc:
                    break
            if found_svc and not await self.keycloak.get_client_role(name, client_id=found_svc):
                await self.keycloak.create_client_role(name, description=name, client_id=found_svc)

        # Set realm role composites to client roles
        await self._set_role_coarse_composites(role.name)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    async def _cleanup_permission_roles(self, svc_client: str) -> int:
        """Delete all client roles on the given service client that are NOT
        in ALL_COARSE_ROLE_NAMES. These are permission-level roles that were
        created by a previous sync and should not appear in the JWT."""
        all_roles = await self.keycloak.get_client_roles(client_id=svc_client)
        cleaned = 0
        for role in all_roles:
            name = role.get("name", "") if isinstance(role, dict) else ""
            if name not in ALL_COARSE_ROLE_NAMES:
                try:
                    await self.keycloak.delete_client_role(name, client_id=svc_client)
                    cleaned += 1
                except Exception as e:
                    logger.warning("Failed to delete role '%s' on '%s': %s", name, svc_client, e)
        return cleaned

    async def _ensure_coarse_roles(self, svc_client: str) -> int:
        """Ensure all coarse roles for a service client exist in Keycloak."""
        created = 0
        for _realm_role_name, coarse_names in COARSE_SERVICE_ROLES[svc_client].items():
            for name in coarse_names:
                exists = await self.keycloak.get_client_role(name, client_id=svc_client)
                if not exists:
                    await self.keycloak.create_client_role(
                        name, description=name, client_id=svc_client
                    )
                    created += 1
        return created

    async def _build_coarse_composite_children(self, role_name: str) -> list[dict[str, Any]]:
        """Build a list of client-role objects for a realm role.
        Uses DB-stored role_ids if available, falls back to hardcoded mapping."""
        # Try to fetch the role's role_ids from DB
        role = await self.role_repo.get_by_name(role_name)

        child_roles: list[dict[str, Any]] = []

        if role and role.role_ids:
            # DB-stored role IDs — resolve service client from COARSE_SERVICE_ROLES
            for name in role.role_ids or []:
                found_svc = None
                for svc_client, realm_map in COARSE_SERVICE_ROLES.items():
                    for svc_names in realm_map.values():
                        if name in svc_names:
                            found_svc = svc_client
                            break
                    if found_svc:
                        break
                if found_svc:
                    child_roles.append(
                        {
                            "name": name,
                            "clientRole": True,
                            "clientId": found_svc,
                        }
                    )
        else:
            # Fallback: hardcoded mapping
            for svc_client, coarse_names in _coarse_roles_for_db_role(role_name).items():
                for name in coarse_names:
                    child_roles.append(
                        {
                            "name": name,
                            "clientRole": True,
                            "clientId": svc_client,
                        }
                    )
        return child_roles

    async def _set_role_coarse_composites(self, role_name: str) -> None:
        child_roles = await self._build_coarse_composite_children(role_name)
        await self.keycloak.set_realm_role_composites(role_name, child_roles)


_composite_role_service_instance: CompositeRoleService | None = None


def get_composite_role_service() -> CompositeRoleService:
    global _composite_role_service_instance
    if _composite_role_service_instance is None:
        _composite_role_service_instance = CompositeRoleService()
    return _composite_role_service_instance
