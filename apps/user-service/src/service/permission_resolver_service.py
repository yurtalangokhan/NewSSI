import time
import uuid

from src.repository import CompositeRoleRepository, UserRepository, UserRoleRepository
from src.service.coarse_role_service import get_role_service


class PermissionResolverService:
    def __init__(self, cache_ttl_seconds: int = 15):
        self.user_repo = UserRepository()
        self.user_role_repo = UserRoleRepository()
        self.role_repo = CompositeRoleRepository()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[uuid.UUID, tuple[float, list[str]]] = {}

    async def resolve_effective_permissions(self, user_id: uuid.UUID) -> list[str]:
        cached = self._cache.get(user_id)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        role_names = await self._role_names_for_user(user_id)
        if not role_names:
            return []

        roles = await self.role_repo.get_by_names(role_names)
        direct_permissions: set[str] = set()
        feature_bundle_names: list[str] = []

        for role in roles:
            permissions = role.permissions or []
            if "*" in permissions or role.name == "system-admin":
                return self._cache_permissions(user_id, ["*"])
            direct_permissions.update(permissions)
            feature_bundle_names.extend(role.role_ids or [])

        if feature_bundle_names:
            bundle_permissions = await get_role_service().get_aggregated_permissions(
                sorted(set(feature_bundle_names))
            )
            if "*" in bundle_permissions:
                return self._cache_permissions(user_id, ["*"])
            direct_permissions.update(bundle_permissions)

        return self._cache_permissions(user_id, sorted(direct_permissions))

    async def _role_names_for_user(self, user_id: uuid.UUID) -> list[str]:
        assignments = await self.user_role_repo.list_user_roles(user_id)
        role_names = [str(role["name"]) for role in assignments]
        if role_names:
            return role_names

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return []
        return [str(user.role)]

    def _cache_permissions(self, user_id: uuid.UUID, permissions: list[str]) -> list[str]:
        if self.cache_ttl_seconds > 0:
            expires_at = time.monotonic() + self.cache_ttl_seconds
            self._cache[user_id] = (expires_at, permissions)
        return permissions

    async def invalidate_user(self, user_id: uuid.UUID) -> None:
        self._cache.pop(user_id, None)


_permission_resolver_service_instance: PermissionResolverService | None = None


def get_permission_resolver_service() -> PermissionResolverService:
    global _permission_resolver_service_instance
    if _permission_resolver_service_instance is None:
        _permission_resolver_service_instance = PermissionResolverService()
    return _permission_resolver_service_instance
