import logging
import uuid
from typing import Any

from i18n import t

from src.core.database.models.user_model import normalize_user_role
from src.core.exceptions import ForbiddenError, NotFoundError
from src.repository import (
    CompositeRoleRepository,
    UserRepository,
    UserRoleRepository,
    UserSettingsRepository,
)

from .keycloak_service import get_keycloak_service
from .permission_resolver_service import get_permission_resolver_service

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.settings_repo = UserSettingsRepository()
        self.role_repo = CompositeRoleRepository()
        self.user_role_repo = UserRoleRepository()
        self.permission_resolver = get_permission_resolver_service()
        self.keycloak = get_keycloak_service()

    async def _logout_keycloak_sessions(self, user) -> None:
        if not self.keycloak.is_enabled() or not getattr(user, "keycloak_id", None):
            return

        logged_out = await self.keycloak.logout_user_sessions(user.keycloak_id)
        if not logged_out:
            raise ValueError(t("user.session_invalidation_failed"))

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        return await self._user_to_app_dict(user)

    async def get_users_by_ids(self, user_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
        users = await self.user_repo.get_by_ids(user_ids)
        return [self._user_to_dict(user) for user in users]

    async def get_user_permissions(self, user_id: uuid.UUID) -> dict[str, list[str]] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        permissions = await self.permission_resolver.resolve_effective_permissions(user_id)
        return {"permissions": permissions}

    async def user_has_permission(self, user_id: uuid.UUID, permission: str) -> dict[str, Any]:
        permission_data = await self.get_user_permissions(user_id)
        if permission_data is None:
            return {"allowed": False, "permissions": []}

        permissions = permission_data.get("permissions", [])
        allowed = permissions == ["*"] or permission in permissions
        return {"allowed": allowed, "permission": permission}

    async def resolve_target_user_id(self, target_id: str) -> uuid.UUID:
        try:
            parsed = uuid.UUID(target_id)
        except ValueError:
            parsed = None

        if parsed is not None:
            by_local_id = await self.user_repo.get_by_id(parsed)
            if by_local_id:
                return by_local_id.id

        by_keycloak_id = await self.user_repo.get_by_keycloak_id(target_id)
        if by_keycloak_id:
            return by_keycloak_id.id

        raise NotFoundError(t("user.target_not_found"))

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
            raise ForbiddenError(t("auth.forbidden")) from None

        if resolved_user_id == authenticated_uuid:
            return resolved_user_id

        user = await self.user_repo.get_by_id(authenticated_uuid)
        if user and await self.user_has_permission(user.id, "user:read"):
            return resolved_user_id

        raise ForbiddenError(t("auth.forbidden"))

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
        if not user:
            return None

        # Fetch role from Keycloak if available (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            try:
                keycloak_role = await self._resolve_role_from_keycloak(user.keycloak_id)
                # Sync Keycloak role to DB if different
                if keycloak_role and keycloak_role != user.role:
                    await self.user_repo.update(uid, role=keycloak_role)
                    user.role = keycloak_role
            except Exception:
                pass

        return await self._user_to_app_dict(user)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        include_external_keycloak_users = self._external_keycloak_enabled()
        users, total = await self.user_repo.list_paginated(
            skip,
            limit,
            query,
            role,
            roles,
            is_active,
            invited,
            include_external_keycloak_users,
        )
        return [self._user_to_dict(u) for u in users], total

    async def get_invited_users(self) -> list[dict[str, Any]]:
        users, _ = await self.user_repo.list_paginated(
            0,
            1000,
            invited=True,
            include_external_keycloak_users=self._external_keycloak_enabled(),
        )
        return [self._user_to_dict(u) for u in users]

    async def create_user(
        self,
        email: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str = "enduser",
        invited: bool = False,
        keycloak_id: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        if await self.user_repo.exists_by_email(email):
            raise ValueError(t("user.already_exists", email=email))

        role_value = role if await self.role_repo.exists(role) else "enduser"
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
        if self.keycloak.is_enabled() and not keycloak_id:
            existing_keycloak_user = await self.keycloak.get_user_by_email(normalized_email)
            if existing_keycloak_user:
                keycloak_id = existing_keycloak_user.get("id")
                if not keycloak_id:
                    raise ValueError(t("user.keycloak_user_missing_id"))
                logger.info(
                    f"Using existing Keycloak user {keycloak_id} for email {normalized_email} "
                    f"(firstName={existing_keycloak_user.get('firstName')}, "
                    f"lastName={existing_keycloak_user.get('lastName')})"
                )
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
                logger.info(
                    f"Creating Keycloak user for {normalized_email}: "
                    f"firstName={keycloak_first_name}, lastName={keycloak_last_name}"
                )

                keycloak_id = await self.keycloak.create_user(keycloak_payload)
                if not keycloak_id:
                    raise ValueError(t("user.keycloak_user_create_failed"))
                created_keycloak_id = True

        if self.keycloak.is_enabled() and not keycloak_id:
            raise ValueError(t("user.keycloak_id_required"))

        if self.keycloak.is_enabled() and keycloak_id and not created_keycloak_id:
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
                    raise ValueError(t("user.keycloak_password_set_failed"))

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
                await self.keycloak.delete_user(keycloak_id)
            raise

        await self.settings_repo.ensure_defaults(user.id)

        if self.keycloak.is_enabled() and keycloak_id:
            await self.keycloak.set_realm_role(keycloak_id, role_value)

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
                role="enduser",
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
                raise ValueError(t("user.already_exists", email=filtered["email"]))

        if "role" in updates and await self.role_repo.exists(updates["role"]):
            filtered["role"] = updates["role"]

        # Get current user first
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Update Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            payload = {}
            # ALWAYS preserve firstName and lastName when updating user
            # to prevent Keycloak from clearing these required attributes
            if "first_name" in filtered:
                first_name = filtered["first_name"]
                # Ensure firstName is never empty
                payload["firstName"] = first_name or user.username or "User"
            elif user.first_name:
                # Preserve existing firstName if not being updated
                payload["firstName"] = user.first_name

            if "last_name" in filtered:
                last_name = filtered["last_name"]
                # Ensure lastName is never empty
                payload["lastName"] = last_name or "User"
            elif user.last_name:
                # Preserve existing lastName if not being updated
                payload["lastName"] = user.last_name

            if "email" in filtered:
                payload["email"] = filtered["email"]
                payload["username"] = filtered["email"]
            if payload:
                logger.info(
                    f"Updating Keycloak user {user.keycloak_id} for {user.email}: "
                    f"firstName={payload.get('firstName')}, lastName={payload.get('lastName')}"
                )
                await self.keycloak.update_user(user.keycloak_id, payload)

            if "role" in filtered:
                role_name = normalize_user_role(filtered["role"])
                await self.keycloak.set_realm_role(user.keycloak_id, role_name)
                await self._logout_keycloak_sessions(user)

        # Then update DB to mirror Keycloak
        user = await self.user_repo.update(user_id, **filtered)
        if not user:
            return None

        return self._user_to_dict(user)

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False

        # Delete from DB first, then from Keycloak
        deleted = await self.user_repo.delete(user_id)
        if not deleted:
            return False

        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.delete_user(user.keycloak_id)

        return True

    async def set_user_active(self, user_id: uuid.UUID, active: bool) -> dict[str, Any] | None:
        # Get current user first
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Update Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            # Always preserve firstName and lastName when updating enabled status
            payload = {"enabled": active}
            if user.first_name:
                payload["firstName"] = user.first_name
            if user.last_name:
                payload["lastName"] = user.last_name
            logger.info(
                f"Setting active={active} for Keycloak user {user.keycloak_id} ({user.email}): "
                f"firstName={payload.get('firstName')}, lastName={payload.get('lastName')}"
            )
            await self.keycloak.update_user(user.keycloak_id, payload)
            if not active and user.is_active:
                await self._logout_keycloak_sessions(user)

        # Then update DB to mirror Keycloak
        user = await self.user_repo.update(user_id, is_active=active)
        if not user:
            return None

        return self._user_to_dict(user)

    async def set_user_role(self, user_id: uuid.UUID, role: str) -> dict[str, Any] | None:
        if not await self.role_repo.exists(role):
            raise ValueError(t("user.invalid_role", role=role))

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Set role in Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_realm_role(user.keycloak_id, role)
            if role != user.role:
                await self._logout_keycloak_sessions(user)
            # Verify role was set correctly by reading back from Keycloak
            try:
                actual_role = await self._resolve_role_from_keycloak(user.keycloak_id)
                # Sync verified role to DB
                user = await self.user_repo.update(user_id, role=actual_role or role)
            except Exception:
                # Fallback: just update DB with requested role
                user = await self.user_repo.update(user_id, role=role)
        else:
            # No Keycloak: update DB only
            user = await self.user_repo.update(user_id, role=role)

        await self.user_role_repo.assign_roles(user_id, [role], primary_role=role)
        await self.permission_resolver.invalidate_user(user_id)
        return self._user_to_dict(user)

    async def list_user_roles(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        roles = await self._roles_or_backfill_primary(user)
        return {"roles": roles}

    async def assign_roles(
        self,
        user_id: uuid.UUID,
        role_names: list[str],
        primary_role: str | None = None,
    ) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        await self._validate_role_names(role_names)
        if primary_role is not None and primary_role not in role_names:
            raise ValueError(t("user.primary_role_must_be_assigned"))

        await self.user_role_repo.assign_roles(user_id, role_names, primary_role=primary_role)
        if primary_role:
            await self._mirror_primary_role(user, primary_role)
        await self.permission_resolver.invalidate_user(user_id)
        return await self.list_user_roles(user_id)

    async def remove_role(self, user_id: uuid.UUID, role_name: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        roles = await self._roles_or_backfill_primary(user)
        if len(roles) <= 1:
            raise ValueError(t("user.cannot_remove_last_role"))

        removed_primary = any(role["name"] == role_name and role["is_primary"] for role in roles)
        removed = await self.user_role_repo.remove_role(user_id, role_name)
        if not removed:
            raise ValueError(t("user.role_not_assigned", role=role_name))

        remaining = await self.user_role_repo.list_user_roles(user_id)
        if removed_primary and remaining:
            new_primary = str(remaining[0]["name"])
            await self.user_role_repo.set_primary_role(user_id, new_primary)
            await self._mirror_primary_role(user, new_primary)
        await self.permission_resolver.invalidate_user(user_id)
        return await self.list_user_roles(user_id)

    async def set_primary_role(self, user_id: uuid.UUID, role_name: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        updated = await self.user_role_repo.set_primary_role(user_id, role_name)
        if not updated:
            raise ValueError(t("user.role_not_assigned", role=role_name))
        await self._mirror_primary_role(user, role_name)
        await self.permission_resolver.invalidate_user(user_id)
        return await self.list_user_roles(user_id)

    async def _validate_role_names(self, role_names: list[str]) -> None:
        existing = await self.role_repo.get_by_names(role_names)
        existing_names = {role.name for role in existing}
        invalid = [role for role in role_names if role not in existing_names]
        if invalid:
            raise ValueError(t("role.invalid_role_ids", roles=invalid))

    async def _roles_or_backfill_primary(self, user) -> list[dict[str, object]]:
        roles = await self.user_role_repo.list_user_roles(user.id)
        if roles:
            return roles
        await self.user_role_repo.assign_roles(user.id, [user.role], primary_role=user.role)
        return await self.user_role_repo.list_user_roles(user.id)

    async def _mirror_primary_role(self, user, role_name: str) -> None:
        await self.user_repo.update(user.id, role=role_name)
        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_realm_role(user.keycloak_id, role_name)
            if role_name != user.role:
                await self._logout_keycloak_sessions(user)

    async def reset_password(self, user_id: uuid.UUID) -> tuple[str, dict[str, Any]]:
        raise ValueError(t("user.password_managed_by_keycloak"))

    async def set_password(self, user_id: uuid.UUID, password: str) -> dict[str, Any] | None:
        raise ValueError(t("user.password_managed_by_keycloak"))

    async def change_password(
        self,
        user_id: uuid.UUID,
        old_password: str,
        new_password: str,
    ) -> dict[str, Any] | None:
        raise ValueError(t("user.password_managed_by_keycloak"))

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
            "role": normalize_user_role(user.role),
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

    async def _resolve_role_from_roles(self, roles: list[dict[str, Any]]) -> str | None:
        """
        Resolve user role from Keycloak role mappings.
        Picks the first role that exists in the local roles DB.
        Returns None when Keycloak only carries stale or non-application roles.
        """
        all_roles = await self.role_repo.get_all()
        valid_role_names = {r.name for r in all_roles}
        role_names = [r.get("name", "").lower() for r in roles if isinstance(r, dict)]
        for name in role_names:
            if name in valid_role_names:
                return name
        return None

    async def _resolve_role_from_realm_roles(self, realm_roles: list[dict[str, Any]]) -> str | None:
        return await self._resolve_role_from_roles(realm_roles)

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
        existing_user = await self.user_repo.get_by_keycloak_id(keycloak_id)
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
            updates["role"] = "enduser"

        user = await self.user_repo.upsert_by_keycloak_id(keycloak_id=keycloak_id, **updates)

        # Ensure settings exist for this user
        await self.settings_repo.ensure_defaults(user.id)

        return self._user_to_dict(user)

    async def get_user_by_keycloak_id(self, keycloak_id: str) -> dict[str, Any] | None:
        """Fetch user by Keycloak ID (subject).

        Called by agent-service /api/me endpoint to get complete user data.
        """
        user = await self.user_repo.get_by_keycloak_id(keycloak_id)
        if not user:
            return None
        return self._user_to_dict(user)

    async def sync_users_from_keycloak(self) -> dict[str, Any]:
        """Sync all users and roles from Keycloak to user-service DB.

        This is a one-time or periodic sync operation that:
        1. Fetches all users from Keycloak
        2. Creates/updates them in user-service DB
        3. Deletes orphaned users (in DB but not in Keycloak)
        4. Syncs realm roles bidirectionally

        Returns a report of the sync operation.
        """
        if not self.keycloak.is_enabled():
            return {"status": "error", "message": "Keycloak is not enabled"}

        report = {
            "keycloak_users_synced": 0,
            "keycloak_users_created": 0,
            "keycloak_users_updated": 0,
            "orphaned_users_deleted": 0,
            "roles_synced": 0,
            "errors": [],
        }

        try:
            # Step 1: Ensure realm roles exist in Keycloak
            await self._ensure_keycloak_roles()
            all_roles = await self.role_repo.get_all()
            report["roles_synced"] = len(all_roles)

            # Step 2: Get all users from Keycloak
            keycloak_users = await self.keycloak.list_users(first=0, max=10000)
            keycloak_ids_set = set()

            # Step 3: Sync each Keycloak user to DB
            for kc_user in keycloak_users:
                try:
                    keycloak_id = kc_user.get("id")
                    if not keycloak_id:
                        continue

                    keycloak_ids_set.add(keycloak_id)
                    email = kc_user.get("email", "").lower()
                    if not email:
                        continue

                    is_external_user = await self._is_external_keycloak_user(keycloak_id)
                    # Check if user exists in DB
                    existing_user = await self.user_repo.get_by_keycloak_id(keycloak_id)
                    resolved_role = await self._resolve_role_from_keycloak(keycloak_id)
                    role = resolved_role or (existing_user.role if existing_user else "enduser")

                    if existing_user:
                        await self.user_repo.update(
                            existing_user.id,
                            email=email,
                            first_name=kc_user.get("firstName"),
                            last_name=kc_user.get("lastName"),
                            username=kc_user.get("username"),
                            is_active=kc_user.get("enabled", True),
                            role=role,
                            is_external_keycloak_user=is_external_user,
                        )
                        report["keycloak_users_updated"] += 1
                    else:
                        # Create new user
                        user = await self.user_repo.create(
                            keycloak_id=keycloak_id,
                            email=email,
                            first_name=kc_user.get("firstName"),
                            last_name=kc_user.get("lastName"),
                            username=kc_user.get("username"),
                            is_active=kc_user.get("enabled", True),
                            is_verified=True,
                            role=role,
                            is_external_keycloak_user=is_external_user,
                        )
                        await self.settings_repo.ensure_defaults(user.id)
                        report["keycloak_users_created"] += 1

                    report["keycloak_users_synced"] += 1
                except Exception as e:
                    report["errors"].append(
                        f"Error syncing Keycloak user {kc_user.get('email', 'unknown')}: {str(e)}"
                    )

            # Step 4: Delete orphaned users (in DB but not in Keycloak)
            all_db_users = await self.user_repo.get_all()
            for db_user in all_db_users:
                if db_user.keycloak_id and db_user.keycloak_id not in keycloak_ids_set:
                    try:
                        await self.user_repo.delete(db_user.id)
                        report["orphaned_users_deleted"] += 1
                    except Exception as e:
                        report["errors"].append(
                            f"Error deleting orphaned user {db_user.email}: {str(e)}"
                        )

            report["status"] = "success"
        except Exception as e:
            report["status"] = "error"
            report["errors"].append(f"Sync operation failed: {str(e)}")

        return report

    async def _ensure_keycloak_roles(self) -> None:
        """Ensure all known DB roles exist in Keycloak during the migration window."""
        all_roles = await self.role_repo.get_all()
        for role in all_roles:
            existing_role = await self.keycloak.get_realm_role(role.name)
            if not existing_role:
                await self.keycloak.create_realm_role(
                    role.name,
                    description=role.description or f"AgenticAI {role.name} role",
                )

    async def _resolve_role_from_keycloak(self, keycloak_id: str) -> str | None:
        realm_roles = await self.keycloak.get_user_realm_roles(keycloak_id)
        if realm_roles:
            return await self._resolve_role_from_roles(realm_roles)

        client_roles = await self.keycloak.get_user_client_roles(keycloak_id)
        if client_roles:
            return await self._resolve_role_from_roles(client_roles)
        return None

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
        except Exception:
            return False


_user_service: UserService | None = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
