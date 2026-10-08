from contextlib import nullcontext
import time
import uuid

from cachetools import LRUCache

from src.core.permissions.admin_roles import is_admin_role_name
from src.repository import CompositeRoleRepository, UserRepository, UserRoleRepository


class PermissionResolverService:
    def __init__(self, cache_ttl_seconds: int = 15):
        self.user_repo = UserRepository()
        self.user_role_repo = UserRoleRepository()
        self.role_repo = CompositeRoleRepository()
        self.cache_ttl_seconds = cache_ttl_seconds
        # Bounded: an unbounded dict here grew one entry per user ever
        # permission-checked, for the lifetime of the process.
        self._cache: LRUCache[uuid.UUID, tuple[float, list[str], bool]] = LRUCache(maxsize=10_000)

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

        keycloak = getattr(self.user_repo, "keycloak", None)
        scope = getattr(type(keycloak), "admin_request_scope", None)
        async with scope(keycloak) if scope else nullcontext():
            return await self._resolve_uncached_access(user_id)

    async def _resolve_uncached_access(self, user_id):
        # Keycloak expands realm-role composites into their feature bundles, so
        # the expanded grants per token role are already the complete answer.
        permissions = set(await self.user_role_repo.effective_client_permissions(user_id))
        if "*" in permissions:
            return self._cache_access(user_id, ["*"], True)
        role_names = await self._role_names_for_user(user_id)
        if not role_names:
            return self._cache_access(user_id, sorted(permissions), False)

        access_by_role = await self.role_repo.get_access_by_names(role_names)
        is_admin = any(is_admin_role_name(name) for name in access_by_role)
        for granted in access_by_role.values():
            if "*" in granted:
                return self._cache_access(user_id, ["*"], True)
            permissions.update(granted)
        return self._cache_access(user_id, sorted(permissions), is_admin)

    async def resolve_effective_permissions(self, user_id: uuid.UUID) -> list[str]:
        permissions, _ = await self.resolve_effective_access(user_id)
        return permissions

    async def _role_names_for_user(self, user_id: uuid.UUID) -> list[str]:
        assignments = await self.user_role_repo.list_user_roles(user_id)
        role_names = [str(role["name"]) for role in assignments]
        return role_names

    def _cache_access(self, user_id: uuid.UUID, permissions: list[str], is_admin: bool) -> tuple[list[str], bool]:
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
