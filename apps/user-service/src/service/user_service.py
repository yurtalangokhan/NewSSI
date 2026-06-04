import secrets
import uuid
from typing import Any

from src.core.database.models.user_model import UserRole, normalize_user_role
from src.repository import SessionRepository, UserRepository, UserSettingsRepository

from .auth_service import AuthService
from .keycloak_service import get_keycloak_service

_KEYCLOAK_ROLES = ["admin", "enduser"]


class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.settings_repo = UserSettingsRepository()
        self.session_repo = SessionRepository()
        self.keycloak = get_keycloak_service()
        self.auth = AuthService()

    async def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        return self._user_to_dict(user)

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
                realm_roles = await self.keycloak.get_user_realm_roles(user.keycloak_id)
                if realm_roles:
                    keycloak_role = self._resolve_role_from_realm_roles(realm_roles)
                    # Sync Keycloak role to DB if different
                    if keycloak_role != user.role:
                        await self.user_repo.update(uid, role=keycloak_role)
                        user.role = keycloak_role
            except Exception:
                pass

        return self._user_to_dict(user)

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
        users, total = await self.user_repo.list_paginated(
            skip,
            limit,
            query,
            role,
            roles,
            is_active,
            invited,
        )
        return [self._user_to_dict(u) for u in users], total

    async def get_invited_users(self) -> list[dict[str, Any]]:
        users, _ = await self.user_repo.list_paginated(0, 1000, invited=True)
        return [self._user_to_dict(u) for u in users]

    async def create_user(
        self,
        email: str,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str = "enduser",
        password: str | None = None,
        invited: bool = False,
        keycloak_id: str | None = None,
    ) -> dict[str, Any]:
        if await self.user_repo.exists_by_email(email):
            raise ValueError(f"User with email {email} already exists")

        role_value = role if role in [r.value for r in UserRole] else UserRole.ENDUSER.value
        hashed_password = AuthService.hash_password(password) if password else None
        normalized_email = email.lower()
        normalized_username = username or normalized_email.split("@")[0]

        created_keycloak_id = False
        if self.keycloak.is_enabled() and not keycloak_id:
            existing_keycloak_user = await self.keycloak.get_user_by_email(normalized_email)
            if existing_keycloak_user:
                keycloak_id = existing_keycloak_user.get("id")
                if not keycloak_id:
                    raise ValueError("Existing Keycloak user has no id")
            else:
                keycloak_payload: dict[str, Any] = {
                    "email": normalized_email,
                    "username": normalized_username,
                    "firstName": first_name,
                    "lastName": last_name,
                    "enabled": True,
                    "emailVerified": True,
                }
                if password:
                    keycloak_payload["credentials"] = [
                        {"type": "password", "value": password, "temporary": False}
                    ]
                else:
                    keycloak_payload["requiredActions"] = ["UPDATE_PASSWORD"]

                keycloak_id = await self.keycloak.create_user(keycloak_payload)
                if not keycloak_id:
                    raise ValueError("Keycloak user could not be created")
                created_keycloak_id = True

        if self.keycloak.is_enabled() and not keycloak_id:
            raise ValueError("Keycloak user id is required")

        if self.keycloak.is_enabled() and keycloak_id and not created_keycloak_id:
            keycloak_payload: dict[str, Any] = {
                "email": normalized_email,
                "username": normalized_username,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "emailVerified": True,
            }
            if password:
                await self.keycloak.set_password(keycloak_id, password, temporary=False)

            await self.keycloak.update_user(keycloak_id, keycloak_payload)

        try:
            user = await self.user_repo.create(
                email=normalized_email,
                username=normalized_username,
                first_name=first_name,
                last_name=last_name,
                role=role_value,
                hashed_password=hashed_password,
                invited=invited,
                password_configured=bool(password),
                keycloak_id=keycloak_id,
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
                role=UserRole.ENDUSER.value,
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
                raise ValueError(f"User with email {filtered['email']} already exists")

        if "role" in updates and updates["role"] in [r.value for r in UserRole]:
            filtered["role"] = updates["role"]

        # Get current user first
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Update Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            payload = {}
            if "first_name" in filtered:
                payload["firstName"] = filtered["first_name"]
            if "last_name" in filtered:
                payload["lastName"] = filtered["last_name"]
            if "email" in filtered:
                payload["email"] = filtered["email"]
                payload["username"] = filtered["email"]
            if payload:
                await self.keycloak.update_user(user.keycloak_id, payload)

            if "role" in filtered:
                await self.keycloak.set_realm_role(
                    user.keycloak_id, normalize_user_role(filtered["role"])
                )

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
            await self.keycloak.update_user(user.keycloak_id, {"enabled": active})

        # Then update DB to mirror Keycloak
        user = await self.user_repo.update(user_id, is_active=active)
        if not user:
            return None

        return self._user_to_dict(user)

    async def set_user_role(self, user_id: uuid.UUID, role: str) -> dict[str, Any] | None:
        if role not in _KEYCLOAK_ROLES:
            raise ValueError(f"Invalid role: {role}")

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Set role in Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_realm_role(user.keycloak_id, role)
            # Verify role was set correctly by reading back from Keycloak
            try:
                realm_roles = await self.keycloak.get_user_realm_roles(user.keycloak_id)
                actual_role = self._resolve_role_from_realm_roles(realm_roles)
                # Sync verified role to DB
                user = await self.user_repo.update(user_id, role=actual_role)
            except Exception:
                # Fallback: just update DB with requested role
                user = await self.user_repo.update(user_id, role=role)
        else:
            # No Keycloak: update DB only
            user = await self.user_repo.update(user_id, role=role)

        return self._user_to_dict(user)

    async def reset_password(self, user_id: uuid.UUID) -> tuple[str, dict[str, Any]]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        new_password = secrets.token_urlsafe(10)
        hashed = AuthService.hash_password(new_password)

        # Update Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_password(user.keycloak_id, new_password, temporary=False)

        # Then update DB to mirror Keycloak
        await self.user_repo.update(
            user_id, hashed_password=hashed, password_configured=True, invited=False
        )

        return new_password, self._user_to_dict(await self.user_repo.get_by_id(user_id))

    async def set_password(self, user_id: uuid.UUID, password: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Update Keycloak first (source of truth)
        if self.keycloak.is_enabled() and user.keycloak_id:
            await self.keycloak.set_password(user.keycloak_id, password, temporary=False)

        # Then update DB to mirror Keycloak
        hashed = AuthService.hash_password(password)
        user = await self.user_repo.update(
            user_id, hashed_password=hashed, password_configured=True, invited=False
        )

        return self._user_to_dict(user)

    def _user_to_dict(self, user) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_superuser": user.is_superuser,
            "role": normalize_user_role(user.role),
            "invited": user.invited,
            "password_configured": user.password_configured,
            "team_name": user.team_name,
            "keycloak_id": user.keycloak_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }

    @staticmethod
    def _resolve_role_from_realm_roles(realm_roles: list[dict[str, Any]]) -> str:
        """
        Extract admin role from Keycloak realm roles.
        Looks for admin-like roles and returns 'admin' if found, else 'enduser'.
        """
        role_names = [r.get("name", "").lower() for r in realm_roles if isinstance(r, dict)]
        admin_indicators = {"admin", "super_admin", "superuser", "realm-admin"}
        for role in role_names:
            if role in admin_indicators:
                return "admin"
        return "enduser"

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
        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id=keycloak_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            username=username,
            is_active=True,
            is_verified=True,
        )

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
            report["roles_synced"] = len(_KEYCLOAK_ROLES)

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

                    # Fetch user's roles from Keycloak
                    realm_roles = await self.keycloak.get_user_realm_roles(keycloak_id)
                    role = self._resolve_role_from_realm_roles(realm_roles)

                    # Check if user exists in DB
                    existing_user = await self.user_repo.get_by_keycloak_id(keycloak_id)

                    if existing_user:
                        await self.user_repo.update(
                            existing_user.id,
                            email=email,
                            first_name=kc_user.get("firstName"),
                            last_name=kc_user.get("lastName"),
                            username=kc_user.get("username"),
                            is_active=kc_user.get("enabled", True),
                            role=role,
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
        """Ensure all required realm roles exist in Keycloak."""
        for role_name in _KEYCLOAK_ROLES:
            existing_role = await self.keycloak.get_realm_role(role_name)
            if not existing_role:
                await self.keycloak.create_realm_role(
                    role_name,
                    description=f"AgenticAI {role_name} role",
                )


_user_service: UserService | None = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
