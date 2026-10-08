"""Who may see and run a persona.

The policy lives apart from ``PersonaService`` because it has two callers.
``ConnectorToolService`` has to answer the same question before it hands out a
datasource credential, and reaching into ``PersonaService`` for it made the two
services import each other — a cycle only survivable through function-local
imports.

Nothing here touches persona persistence: callers load the persona row and pass
it in, so this module depends on permissions alone and neither service package
has to know about the other.
"""

from __future__ import annotations

from typing import Any

from core.observability.logger import get_logger
from service.auth.auth_service import AuthenticatedUser

logger = get_logger(__name__)

#: Identities the platform provisions itself, which bypass permission lookups.
_PLATFORM_USER_IDS = frozenset({"internal-service"})


def permission_user_id(user: AuthenticatedUser) -> str:
    """Return the id permissions are recorded against.

    A Keycloak subject and the local user-service id are different values, and
    permissions hang off the latter when the token carries it.
    """
    user_service_user = getattr(user, "claims", {}).get("user_service_user")
    if isinstance(user_service_user, dict) and user_service_user.get("id"):
        return str(user_service_user["id"])
    return user.user_id


def group_persona_ids(groups: list[dict[str, Any]]) -> set[int]:
    """Collect persona ids out of agent-group rows, skipping unparsable ones."""
    persona_ids: set[int] = set()
    for group in groups:
        for persona_id in group.get("persona_ids", []) or []:
            try:
                persona_ids.add(int(persona_id))
            except (TypeError, ValueError):
                continue
    return persona_ids


class PersonaAccessPolicy:
    """Decides persona visibility for a user."""

    async def can_manage_all(self, user: AuthenticatedUser) -> bool:
        """True when *user* administers every persona, so no filtering applies."""
        if user.user_id in _PLATFORM_USER_IDS:
            return True

        from integrations.user_service_client import get_user_permissions

        try:
            permissions = await get_user_permissions(permission_user_id(user), user.access_token)
            return permissions.get("is_admin") is True or "*" in permissions.get("permissions", [])
        except Exception:
            # Fail closed: an unreachable permission service must narrow what
            # the caller sees, never widen it.
            logger.warning("Could not check global agent access", exc_info=True)
            return False

    async def load_visibility(self, user: AuthenticatedUser) -> tuple[set[int], set[int]]:
        """Return ``(restricted_persona_ids, accessible_persona_ids)`` for *user*."""
        from service.auth.permission_service import get_permission_service

        resource_ids = await get_permission_service().get_user_accessible_agents(
            permission_user_id(user), required_permission="execute"
        )
        accessible_persona_ids = group_persona_ids([{"persona_ids": resource_ids}])
        return set(), accessible_persona_ids

    def can_access(
        self,
        persona: dict[str, Any],
        user: AuthenticatedUser,
        restricted_persona_ids: set[int],
        accessible_persona_ids: set[int],
        can_manage_all_personas: bool,
    ) -> bool:
        """True when *user* may see and run *persona*."""
        if can_manage_all_personas:
            return True

        persona_id = int(persona["id"])
        if str(persona.get("user_id") or "") in {user.user_id, permission_user_id(user)}:
            return True

        if persona_id in accessible_persona_ids:
            return True

        if persona_id in restricted_persona_ids:
            return persona_id in accessible_persona_ids

        return bool(persona.get("is_public", True))


_policy = PersonaAccessPolicy()


def get_persona_access_policy() -> PersonaAccessPolicy:
    """Return the shared policy. It holds no state; the instance is a convenience."""
    return _policy
