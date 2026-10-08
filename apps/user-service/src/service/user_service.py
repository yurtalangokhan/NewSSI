from contextlib import nullcontext
from typing import Any
import uuid

from error_contract import (
    ApplicationError,
    BadRequestError,
    ConflictError,
    DependencyResponseError,
    DependencyUnavailableError,
    InternalServerError,
    UserNotFoundError,
)

from src.core.exceptions import ForbiddenError, NotFoundError
from src.core.observability import get_logger, pseudonym
from src.core.permissions.roles import DEFAULT_ROLE_NAME, display_role_name
from src.repository import (
    CompositeRoleRepository,
    UserRepository,
    UserRoleRepository,
    UserSettingsRepository,
)

from .keycloak_service import get_keycloak_service
from .permission_resolver_service import get_permission_resolver_service

logger = get_logger(__name__)


class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.settings_repo = UserSettingsRepository()
        self.role_repo = CompositeRoleRepository()
        self.user_role_repo = UserRoleRepository()
        self.permission_resolver = get_permission_resolver_service()
        self.keycloak = get_keycloak_service()

    async def _logout_keycloak_sessions(self, user) -> None:
        if not getattr(user, "keycloak_id", None):
            return

        logged_out = await self.keycloak.logout_user_sessions(user.keycloak_id)
        if not logged_out:
            raise DependencyUnavailableError(
                message_key="errors.user_service.user.session_invalidation_failed",
                message_params={},
            )

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        return await self._user_to_app_dict(user)

    async def get_users_by_ids(self, user_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
        users = await self.user_repo.get_by_ids(user_ids)
        return [self._user_to_dict(user) for user in users]

    async def get_user_permissions(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        scope = getattr(type(self.keycloak), "admin_request_scope", None)
        async with scope(self.keycloak) if scope else nullcontext():
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                return None
            permissions, is_admin = await self.permission_resolver.resolve_effective_access(user_id)
            return {"permissions": permissions, "is_admin": is_admin}

    async def user_has_permission(self, user_id: uuid.UUID, permission: str) -> dict[str, Any]:
        permission_data = await self.get_user_permissions(user_id)
        if permission_data is None:
            return {"allowed": False, "permissions": []}

        permissions = permission_data.get("permissions", [])
        allowed = permissions == ["*"] or permission in permissions
        return {"allowed": allowed, "permission": permission}

    async def resolve_target_user_id(self, target_id: str) -> uuid.UUID:
        try:
            user = await self.user_repo.get_by_id(uuid.UUID(target_id))
        except ValueError:
            user = None
        if user:
            return user.id
        raise UserNotFoundError()

    async def authorize_target_user_id(
        self,
        target_id: str,
        authenticated_user_id: str,
    ) -> uuid.UUID:
        resolved_user_id = await self.resolve_target_user_id(target_id)

        if authenticated_user_id == "internal-service":
            return resolved_user_id

        try:
            authenticated_uuid = uuid.UUID(authenticated_user_id)
        except ValueError:
            raise ForbiddenError() from None

        if resolved_user_id == authenticated_uuid:
            return resolved_user_id

        user = await self.user_repo.get_by_id(authenticated_uuid)
        if user and (await self.user_has_permission(user.id, "user:read")).get("allowed", False):
            return resolved_user_id

        raise ForbiddenError()

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_email(email)
        if not user:
            return None
        return self._user_to_dict(user)

    async def get_current_user(self, user_id: str) -> dict[str, Any] | None:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            return None
        user = await self.user_repo.get_by_id(uid)
        return await self._user_to_app_dict(user) if user else None

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int, bool]:
        include_external_keycloak_users = self._external_keycloak_enabled()
        users, total, exact = await self.user_repo.list_paginated(
            skip,
            limit,
            query,
            role,
            roles,
            is_active,
            invited,
            include_external_keycloak_users,
        )
        return [self._user_to_dict(u) for u in users], total, exact

    async def get_invited_users(self) -> list[dict[str, Any]]:
        users, _, _ = await self.user_repo.list_paginated(
            0,
            1000,
            invited=True,
            include_external_keycloak_users=self._external_keycloak_enabled(),
        )
        return [self._user_to_dict(u) for u in users]

    async def get_role_distribution(self) -> dict[str, Any]:
        """Primary-role counts from a background-refreshed snapshot; never blocks on Keycloak."""
        from .role_distribution import get_role_distribution_snapshot

        return await get_role_distribution_snapshot().read()

    async def create_user(
        self,
        email: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role_id: str | None = None,
        invited: bool = False,
        keycloak_id: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        if await self.user_repo.exists_by_email(email):
            raise ConflictError(
                message_key="errors.user_service.user.already_exists",
                message_params={"email": email},
            )

        role_value = (await self._roles_by_ids([role_id]))[0].name if role_id else DEFAULT_ROLE_NAME
        normalized_email = email.lower()
        normalized_username = username or normalized_email.split("@")[0]
        normalized_first_name = (first_name or "").strip() or normalized_username
        normalized_last_name = (last_name or "").strip() or "User"
        normalized_password = password.strip() if password else None

        # Ensure firstName and lastName are never empty for Keycloak
        # (Keycloak may require these as non-empty for User Profile validation)
        keycloak_first_name = normalized_first_name or normalized_username
        keycloak_last_name = normalized_last_name or "User"

        created_keycloak_id = False
        if not keycloak_id:
            existing_keycloak_user = await self.keycloak.get_user_by_email(normalized_email)
            if existing_keycloak_user:
                keycloak_id = existing_keycloak_user.get("id")
                if not keycloak_id:
                    raise DependencyResponseError(
                        message_key="errors.user_service.user.keycloak_user_missing_id",
                        message_params={},
                    )
                logger.info("Using existing Keycloak user %s", keycloak_id)
            else:
                keycloak_payload: dict[str, Any] = {
                    "email": normalized_email,
                    "username": normalized_username,
                    "firstName": keycloak_first_name,
                    "lastName": keycloak_last_name,
                    "enabled": True,
                    "emailVerified": True,
                    "requiredActions": [],
                }
                if normalized_password:
                    keycloak_payload["credentials"] = [
                        {
                            "type": "password",
                            "value": normalized_password,
                            "temporary": False,
                        }
                    ]
                logger.info("Creating Keycloak user for %s", pseudonym(normalized_username))

                keycloak_id = await self.keycloak.create_user(keycloak_payload)
                if not keycloak_id:
                    raise DependencyResponseError(
                        message_key="errors.user_service.user.keycloak_user_create_failed",
                        message_params={},
                    )
                created_keycloak_id = True

        if not keycloak_id:
            raise BadRequestError(message_key="errors.user_service.user.keycloak_id_required", message_params={})

        if not created_keycloak_id:
            keycloak_payload: dict[str, Any] = {
                "email": normalized_email,
                "username": normalized_username,
                "firstName": keycloak_first_name,
                "lastName": keycloak_last_name,
                "enabled": True,
                "emailVerified": True,
                "requiredActions": [],
            }
            await self.keycloak.update_user(keycloak_id, keycloak_payload)
            if normalized_password:
                password_set = await self.keycloak.set_password(
                    keycloak_id,
                    normalized_password,
                    temporary=False,
                )
                if not password_set:
                    raise DependencyResponseError(
                        message_key="errors.user_service.user.keycloak_password_set_failed",
                        message_params={},
                    )

        try:
            user = await self.user_repo.create(
                email=normalized_email,
                username=normalized_username,
                first_name=normalized_first_name,
                last_name=normalized_last_name,
                role=role_value,
                hashed_password=None,
                invited=invited,
                password_configured=bool(normalized_password),
                keycloak_id=keycloak_id,
                is_external_keycloak_user=False,
            )
        except Exception:
            if created_keycloak_id and keycloak_id:
                try:
                    await self.keycloak.delete_user(keycloak_id)
                except Exception:
                    logger.exception("Failed to clean up Keycloak user after creation failure")
            raise

        await self.settings_repo.ensure_defaults(user.id)

        await self.user_role_repo.replace_roles(user.id, [role_value], primary_role=role_value)
        user = await self.user_repo.get_by_id(user.id)

        return self._user_to_dict(user)

    async def invite_users(self, emails: list[str]) -> list[dict[str, Any]]:
        users = []
        for email in emails:
            if await self.user_repo.exists_by_email(email):
                continue
            user = await self.create_user(
                email=email,
                username=None,
                first_name=None,
                last_name=None,
                invited=True,
            )
            users.append(user)
        return users

    async def update_user(self, user_id: uuid.UUID, **updates) -> dict[str, Any] | None:
        allowed = {
            "first_name",
            "last_name",
            "email",
            "username",
            "team_name",
            "is_active",
            "is_verified",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if "email" in filtered:
            existing = await self.user_repo.get_by_email(filtered["email"])
            if existing and existing.id != user_id:
                raise ConflictError(
                    message_key="errors.user_service.user.already_exists",
                    message_params={"email": filtered["email"]},
                )
        user = await self.user_repo.update(user_id, **filtered)
        if user is None:
            return None
        if filtered.get("is_active") is False:
            await self._logout_keycloak_sessions(user)
        return self._user_to_dict(user)

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        deleted = await self.user_repo.delete(user_id)
        if deleted:
            from src.repository import ApiKeyRepository, UserMemoryRepository
            from src.repository.keycloak_resource_authorization import (
                project_resource_permission_mutation,
            )
            from src.repository.resource_permission_repository import ResourcePermissionRepository

            await self.settings_repo.delete(user_id)
            await ApiKeyRepository().delete_by_user(user_id)
            await UserMemoryRepository().delete_all(user_id)
            permissions = ResourcePermissionRepository()
            await project_resource_permission_mutation(lambda: permissions.delete_user_permissions(user_id))
            await self.permission_resolver.invalidate_user(user_id)
        return deleted

    async def set_user_active(self, user_id: uuid.UUID, active: bool) -> dict[str, Any] | None:
        return await self.update_user(user_id, is_active=active)

    async def replace_role(self, user_id: uuid.UUID, role_id: str) -> dict[str, Any] | None:
        """Make the platform role with this Keycloak ID the user's only realm role."""
        (role,) = await self._roles_by_ids([role_id])
        return await self._replace_role(user_id, role.name)

    async def set_user_role(self, user_id: uuid.UUID, role_name: str) -> dict[str, Any] | None:
        """Replace the user's realm role by name; organization membership roles are names."""
        if not await self.role_repo.get_by_name(role_name):
            raise BadRequestError(
                message_key="errors.user_service.role.invalid_role_ids",
                message_params={"roles": [role_name]},
            )
        return await self._replace_role(user_id, role_name)

    async def _replace_role(self, user_id: uuid.UUID, role_name: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            return None
        await self.user_role_repo.replace_roles(user_id, [role_name], primary_role=role_name)
        await self.permission_resolver.invalidate_user(user_id)
        await self._logout_keycloak_sessions(user)
        return self._user_to_dict(await self.user_repo.get_by_id(user_id))

    async def list_user_roles(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        return {"roles": await self.user_role_repo.list_user_roles(user_id)}

    async def assign_roles(
        self,
        user_id: uuid.UUID,
        role_ids: list[str],
        primary_role_id: str | None = None,
    ) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        if primary_role_id is not None and primary_role_id not in role_ids:
            raise BadRequestError(message_key="errors.user_service.user.primary_role_must_be_assigned")
        roles = await self._roles_by_ids(role_ids)
        primary = next((r.name for r in roles if r.id == primary_role_id), None)
        await self.user_role_repo.assign_roles(user_id, [role.name for role in roles], primary_role=primary)
        if primary:
            await self._mirror_primary_role(user, primary)
        await self.permission_resolver.invalidate_user(user_id)
        return await self.list_user_roles(user_id)

    async def remove_role(self, user_id: uuid.UUID, role_id: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        assignments = await self.user_role_repo.list_user_roles(user_id)
        if len(assignments) <= 1:
            raise ConflictError(message_key="errors.user_service.user.cannot_remove_last_role", message_params={})
        target = self._assignment(assignments, role_id)
        if not await self.user_role_repo.remove_role(user_id, target["name"]):
            raise NotFoundError(
                message_key="errors.user_service.user.role_not_assigned",
                message_params={"role": role_id},
            )

        remaining = await self.user_role_repo.list_user_roles(user_id)
        if target["is_primary"] and remaining:
            await self.user_role_repo.set_primary_role(user_id, str(remaining[0]["name"]))
        await self._logout_keycloak_sessions(user)
        await self.permission_resolver.invalidate_user(user_id)
        return await self.list_user_roles(user_id)

    async def set_primary_role(self, user_id: uuid.UUID, role_id: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        assignments = await self.user_role_repo.list_user_roles(user_id)
        role_name = str(self._assignment(assignments, role_id)["name"])
        if not await self.user_role_repo.set_primary_role(user_id, role_name):
            raise NotFoundError(
                message_key="errors.user_service.user.role_not_assigned",
                message_params={"role": role_id},
            )
        await self._mirror_primary_role(user, role_name)
        await self.permission_resolver.invalidate_user(user_id)
        return await self.list_user_roles(user_id)

    @staticmethod
    def _assignment(assignments: list[dict[str, Any]], role_id: str) -> dict[str, Any]:
        match = next((a for a in assignments if a.get("id") == role_id), None)
        if match is None:
            raise NotFoundError(
                message_key="errors.user_service.user.role_not_assigned",
                message_params={"role": role_id},
            )
        return match

    async def _roles_by_ids(self, role_ids: list[str]):
        """Resolve Keycloak realm-role IDs, preserving order; unknown IDs are rejected."""
        by_id = {role.id: role for role in await self.role_repo.get_by_ids(role_ids)}
        invalid = [role_id for role_id in role_ids if role_id not in by_id]
        if invalid:
            raise BadRequestError(
                message_key="errors.user_service.role.invalid_role_ids",
                message_params={"roles": invalid},
            )
        return [by_id[role_id] for role_id in dict.fromkeys(role_ids)]

    async def _mirror_primary_role(self, user, role_name: str) -> None:
        # Primary-role metadata is already written by the assignment repository.
        # Selecting a display role must not replace the user's other grants.
        if role_name != user.role:
            await self._logout_keycloak_sessions(user)

    # Keycloak owns credential lifecycle; these interface stubs reject.
    async def reset_password(self, user_id: uuid.UUID) -> tuple[str, dict[str, Any]]:  # noqa: ARG002
        raise ForbiddenError(message_key="errors.user_service.user.password_managed_by_keycloak", message_params={})

    async def set_password(self, user_id: uuid.UUID, password: str) -> dict[str, Any] | None:  # noqa: ARG002
        raise ForbiddenError(message_key="errors.user_service.user.password_managed_by_keycloak", message_params={})

    async def change_password(
        self,
        user_id: uuid.UUID,  # noqa: ARG002
        old_password: str,  # noqa: ARG002
        new_password: str,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        raise ForbiddenError(message_key="errors.user_service.user.password_managed_by_keycloak", message_params={})

    def _user_to_dict(self, user) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or None,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "role": display_role_name(user.role),
            "invited": user.invited,
            "password_configured": user.password_configured,
            "is_external_keycloak_user": getattr(user, "is_external_keycloak_user", False),
            "groups": getattr(user, "groups", []) or [],
            "team_name": user.team_name,
            "keycloak_id": user.keycloak_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }

    async def _user_to_app_dict(self, user) -> dict[str, Any]:
        payload = self._user_to_dict(user)
        settings = await self.settings_repo.ensure_defaults(user.id)
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None
        payload["preferences"] = {
            "chosen_assistants": None,
            "visible_assistants": [],
            "hidden_assistants": [],
            "pinned_assistants": settings.pinned_assistants,
            "default_model": settings.default_model,
            "default_provider_id": settings.default_provider_id,
            "recent_assistants": [],
            "auto_scroll": settings.auto_scroll,
            "shortcut_enabled": settings.shortcut_enabled,
            "temperature_override_enabled": False,
            "theme_preference": settings.theme_preference,
            "chat_background": settings.chat_background,
            "default_app_mode": settings.default_app_mode,
        }
        payload["personalization"] = {
            "name": full_name or user.username or user.email.split("@", 1)[0],
            "role": settings.work_role or "",
            "memories": settings.memories or [],
            "use_memories": settings.use_memories,
            "enable_memory_tool": settings.enable_memory_tool,
            "user_preferences": settings.user_preferences or "",
            "long_term_memory_enabled": settings.long_term_memory_enabled,
            "extract_memory": settings.extract_memory,
        }
        return payload

    async def upsert_user_from_keycloak(
        self,
        keycloak_id: str,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> dict[str, Any]:
        """Create or update user from Keycloak OIDC profile.

        Called by agent-service during OIDC callback to ensure user exists in user-service.
        """
        is_external_user = await self._is_external_keycloak_user(keycloak_id)
        existing_user = await self.user_repo.get_by_id(keycloak_id)
        updates: dict[str, Any] = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "is_active": True,
            "is_verified": True,
            "is_external_keycloak_user": is_external_user,
        }
        if not existing_user:
            updates["role"] = DEFAULT_ROLE_NAME

        user = await self.user_repo.upsert_by_keycloak_id(keycloak_id=keycloak_id, **updates)

        # Ensure settings exist for this user
        await self.settings_repo.ensure_defaults(user.id)

        return self._user_to_dict(user)

    async def get_user_by_keycloak_id(self, keycloak_id: str) -> dict[str, Any] | None:
        """Fetch user by Keycloak ID (subject).

        Called by agent-service /api/me endpoint to get complete user data.
        """
        user = await self.user_repo.get_by_id(keycloak_id)
        if not user:
            return None
        return self._user_to_dict(user)

    async def sync_users_from_keycloak(self) -> dict[str, Any]:
        """Compatibility refresh: identities are already read directly from Keycloak."""
        users = await self.user_repo.get_all()
        return {
            "status": "success",
            "keycloak_users_synced": len(users),
            "keycloak_users_created": 0,
            "keycloak_users_updated": 0,
            "orphaned_users_deleted": 0,
            "roles_synced": 0,
            "errors": [],
        }

    def _external_keycloak_enabled(self) -> bool:
        is_external_keycloak = getattr(self.keycloak, "is_external_keycloak", None)
        return bool(is_external_keycloak()) if callable(is_external_keycloak) else False

    async def _is_external_keycloak_user(self, keycloak_id: str) -> bool:
        if not self._external_keycloak_enabled():
            return False
        user_has_federated_identity = getattr(self.keycloak, "user_has_federated_identity", None)
        if not callable(user_has_federated_identity):
            return False
        try:
            return bool(
                await user_has_federated_identity(
                    keycloak_id,
                    self.keycloak.get_external_keycloak_alias(),
                )
            )
        except ApplicationError:
            raise
        except Exception as exc:
            logger.exception("Failed to resolve external Keycloak identity")
            raise InternalServerError() from exc


_user_service: UserService | None = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
