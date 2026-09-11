import time
import uuid

from src.core.permissions.admin_roles import is_admin_role_name
from src.repository import CompositeRoleRepository, UserRepository, UserRoleRepository
from src.service.coarse_role_service import get_role_service


class PermissionResolverService:
    def __init__(self, cache_ttl_seconds: int = 15):
        self.user_repo = UserRepository()
        self.user_role_repo = UserRoleRepository()
        self.role_repo = CompositeRoleRepository()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[uuid.UUID, tuple[float, list[str], bool]] = {}

    async def resolve_effective_access(self, user_id: uuid.UUID) -> tuple[list[str], bool]:
        """Resolve a user's effective permissions AND whether they hold an
        admin-tier composite role (system-admin / enterprise-admin).

        The admin flag is derived from the user's actual composite role
        assignment(s), never from whether their aggregated permissions
        happen to overlap with what some admin page requires - see
        `src.core.permissions.admin_roles` for why that distinction matters.
        """
        cached = self._cache.get(user_id)
        if cached and cached[0] > time.monotonic():
            return cached[1], cached[2]

        role_names = await self._role_names_for_user(user_id)
        if not role_names:
            return self._cache_access(user_id, [], False)

        direct_permissions: set[str] = set()
        feature_bundle_names: list[str] = []
        is_admin = False

        if hasattr(self.role_repo, "get_access_by_names"):
            access_by_role = await self.role_repo.get_access_by_names(role_names)
            for role_name, access in access_by_role.items():
                if is_admin_role_name(role_name):
                    is_admin = True

                permissions = access.get("permissions", [])
                if "*" in permissions:
                    return self._cache_access(user_id, ["*"], True)
                direct_permissions.update(permissions)
                feature_bundle_names.extend(access.get("role_ids", []))
        else:
            roles = await self.role_repo.get_by_names(role_names)
            for role in roles:
                if is_admin_role_name(role.name):
                    is_admin = True

                permissions = role.permissions or []
                if "*" in permissions:
                    return self._cache_access(user_id, ["*"], True)
                direct_permissions.update(permissions)
                feature_bundle_names.extend(role.role_ids or [])

        if feature_bundle_names:
            bundle_permissions = await get_role_service().get_aggregated_permissions(
                sorted(set(feature_bundle_names))
            )
            if "*" in bundle_permissions:
                return self._cache_access(user_id, ["*"], True)
            direct_permissions.update(bundle_permissions)

        return self._cache_access(user_id, sorted(direct_permissions), is_admin)

    async def resolve_effective_permissions(self, user_id: uuid.UUID) -> list[str]:
        permissions, _ = await self.resolve_effective_access(user_id)
        return permissions

    async def _role_names_for_user(self, user_id: uuid.UUID) -> list[str]:
        assignments = await self.user_role_repo.list_user_roles(user_id)
        role_names = [str(role["name"]) for role in assignments]
        if role_names:
            return role_names

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return []
        return [str(user.role)]

    def _cache_access(
        self, user_id: uuid.UUID, permissions: list[str], is_admin: bool
    ) -> tuple[list[str], bool]:
        if self.cache_ttl_seconds > 0:
            expires_at = time.monotonic() + self.cache_ttl_seconds
            self._cache[user_id] = (expires_at, permissions, is_admin)
        return permissions, is_admin

    async def invalidate_user(self, user_id: uuid.UUID) -> None:
        self._cache.pop(user_id, None)


_permission_resolver_service_instance: PermissionResolverService | None = None


def get_permission_resolver_service() -> PermissionResolverService:
    global _permission_resolver_service_instance
    if _permission_resolver_service_instance is None:
        _permission_resolver_service_instance = PermissionResolverService()
    return _permission_resolver_service_instance
