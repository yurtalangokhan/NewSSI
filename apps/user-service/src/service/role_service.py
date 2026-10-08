import asyncio
from collections.abc import Iterable
from contextlib import AsyncExitStack
from typing import Any

from error_contract import ApplicationError, BadRequestError, DependencyUnavailableError

from src.core.exceptions import ConflictError
from src.core.observability import get_logger
from src.core.permissions.admin_roles import is_admin_role_name
from src.repository import CompositeRoleRepository, PermissionRepository, UserRoleRepository
from src.repository.keycloak_role_client import CompositeRoleRecord, invalidate_role_access

from .coarse_role_service import get_role_service
from .keycloak_service import get_keycloak_service

logger = get_logger(__name__)

_LOGOUT_WAVE = 8


def _to_dict(role: CompositeRoleRecord) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": list(role.permissions),
        "role_ids": list(role.bundle_ids),
        "role_names": list(role.bundle_names),
        "is_builtin": role.is_builtin,
        "is_admin": is_admin_role_name(role.name),
    }


def _bundles_dict(role: CompositeRoleRecord) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "role_ids": list(role.bundle_ids),
        "role_names": list(role.bundle_names),
    }


class CompositeRoleService:
    """Platform (Keycloak realm) roles, addressed by their Keycloak role ID."""

    def __init__(self):
        self.role_repo = CompositeRoleRepository()
        self.permission_repo = PermissionRepository()
        self.user_role_repo = UserRoleRepository()
        self.keycloak = get_keycloak_service()

    async def _invalidate_sessions_for_role_users(self, role_name: str) -> int:
        invalidate_role_access()
        invalidated = 0
        async with AsyncExitStack() as stack:
            scope = getattr(type(self.keycloak), "admin_request_scope", None)
            if scope is not None:
                await stack.enter_async_context(scope(self.keycloak))
            user_ids = [str(i) for i in await self.user_role_repo.list_user_ids_by_role(role_name)]
            for first in range(0, len(user_ids), _LOGOUT_WAVE):
                wave = user_ids[first : first + _LOGOUT_WAVE]
                outcomes = await asyncio.gather(
                    *(self.keycloak.logout_user_sessions(user_id) for user_id in wave),
                    return_exceptions=True,
                )
                for user_id, logged_out in zip(wave, outcomes, strict=True):
                    if isinstance(logged_out, BaseException):
                        if isinstance(logged_out, ApplicationError):
                            raise logged_out
                        raise DependencyUnavailableError() from logged_out
                    if not logged_out:
                        raise DependencyUnavailableError(
                            message_key="errors.user_service.role.session_invalidation_failed_for_user",
                            message_params={"email": user_id},
                        )
                    invalidated += 1
        return invalidated

    async def _validate_permissions(self, permissions: Iterable[str]) -> None:
        valid = {p.name for p in await self.permission_repo.get_all()}
        invalid = [p for p in permissions if p not in valid and p != "*"]
        if invalid:
            raise BadRequestError(
                message_key="errors.user_service.role.invalid_permissions",
                message_params={"permissions": invalid},
            )

    async def _validate_bundle_ids(self, role_ids: Iterable[str]) -> None:
        role_ids = list(role_ids)
        known = {r.id for r in await get_role_service().repo.get_by_ids(role_ids)}
        invalid = [role_id for role_id in role_ids if role_id not in known]
        if invalid:
            raise BadRequestError(
                message_key="errors.user_service.role.invalid_role_ids",
                message_params={"roles": invalid},
            )

    async def _effective_permissions(self, role: CompositeRoleRecord) -> list[str]:
        """Direct grants merged with bundled feature-role grants; ``["*"]`` wins."""
        if "*" in role.permissions:
            return ["*"]
        bundled = await get_role_service().get_aggregated_permissions(role.bundle_ids)
        if "*" in bundled:
            return ["*"]
        return sorted({*role.permissions, *bundled})

    # ----------------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------------

    async def list_roles(self) -> list[dict[str, Any]]:
        return [_to_dict(role) for role in await self.role_repo.get_all()]

    async def get_role(self, role_id: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_id(role_id)
        return _to_dict(role) if role else None

    async def create_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if await self.role_repo.exists(name):
            raise ConflictError(message_key="errors.user_service.role.already_exists", message_params={"name": name})
        await self._validate_permissions(permissions or [])
        await self._validate_bundle_ids(role_ids or [])
        role = await self.role_repo.create(
            name=name,
            description=description,
            permissions=permissions or [],
            bundle_ids=role_ids or [],
        )
        return _to_dict(role)

    async def update_role(
        self,
        role_id: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        if permissions is not None:
            await self._validate_permissions(permissions)
        if role_ids is not None:
            await self._validate_bundle_ids(role_ids)
        role = await self.role_repo.update(
            role_id, description=description, permissions=permissions, bundle_ids=role_ids
        )
        if not role:
            return None
        if permissions is not None or role_ids is not None:
            await self._invalidate_sessions_for_role_users(role.name)
        return _to_dict(role)

    async def delete_role(self, role_id: str) -> bool:
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            return False
        if role.is_builtin:
            raise BadRequestError(
                message_key="errors.user_service.role.cannot_delete_builtin",
                message_params={"name": role.name},
            )
        if await self.user_role_repo.list_user_ids_by_role(role.name):
            raise ConflictError(
                message_key="errors.user_service.role.cannot_delete_in_use",
                message_params={"name": role.name},
            )
        deleted = await self.role_repo.delete(role_id)
        invalidate_role_access()
        return deleted

    # ----------------------------------------------------------------
    # Grants
    # ----------------------------------------------------------------

    async def get_role_permissions(self, role_id: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            return None
        return {**_bundles_dict(role), "permissions": await self._effective_permissions(role)}

    async def set_role_permissions(self, role_id: str, permissions: list[str]) -> dict[str, Any] | None:
        await self._validate_permissions(permissions)
        role = await self.role_repo.update(role_id, permissions=permissions)
        if not role:
            return None
        await self._invalidate_sessions_for_role_users(role.name)
        return {**_bundles_dict(role), "permissions": await self._effective_permissions(role)}

    async def get_role_bundles(self, role_id: str) -> dict[str, Any] | None:
        role = await self.role_repo.get_by_id(role_id)
        return _bundles_dict(role) if role else None

    async def set_role_bundles(self, role_id: str, role_ids: list[str]) -> dict[str, Any] | None:
        await self._validate_bundle_ids(role_ids)
        role = await self.role_repo.update(role_id, bundle_ids=role_ids)
        if not role:
            return None
        await self._invalidate_sessions_for_role_users(role.name)
        return {
            **_bundles_dict(role),
            "effective_permissions": await self._effective_permissions(role),
        }


_composite_role_service_instance: CompositeRoleService | None = None


def get_composite_role_service() -> CompositeRoleService:
    global _composite_role_service_instance
    if _composite_role_service_instance is None:
        _composite_role_service_instance = CompositeRoleService()
    return _composite_role_service_instance
