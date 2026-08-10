"""
Permission checking service for agent-service.

Replaces legacy agent_groups with new organization-based permission system
by delegating to user-service.
"""

import httpx
import logging
from functools import lru_cache
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


class PermissionService:
    """Check resource permissions via user-service."""

    def __init__(self):
        self.settings = get_settings()
        self.user_service_url = self.settings.USER_SERVICE_URL or "http://localhost:8002"
        self.internal_token = getattr(self.settings, "INTERNAL_SERVICE_TOKEN", None)
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=5.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def check_agent_access(
        self,
        user_id: str,
        agent_id: str | int,
        required_permission: str = "execute",
    ) -> dict[str, Any]:
        """
        Check if user can access an agent.

        Args:
            user_id: User UUID or Keycloak ID
            agent_id: Agent/persona ID
            required_permission: "owner", "admin", "write", "read", "execute"

        Returns:
            {
                "allowed": bool,
                "permission_level": str | None,
                "source": "user" | "organization" | "inherited" | "public" | "legacy"
            }
        """
        try:
            client = await self._get_client()
            headers = {}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token

            response = await client.post(
                f"{self.user_service_url}/api/permissions/check",
                json={
                    "user_id": str(user_id),
                    "resource_type": "agent",
                    "resource_id": str(agent_id),
                    "required_permission": required_permission,
                },
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.warning(
                f"Permission check failed for user {user_id}, agent {agent_id}: {e}"
            )
            # Fallback to legacy system
            return await self._check_legacy_access(user_id, agent_id)
        except Exception as e:
            logger.error(f"Unexpected error in permission check: {e}")
            # Fail-safe: allow access if permission system is down
            return {
                "allowed": True,
                "permission_level": "execute",
                "source": "fallback",
            }

    async def _check_legacy_access(
        self, user_id: str, agent_id: str | int
    ) -> dict[str, Any]:
        """
        Fallback: check legacy agent_groups.

        DEPRECATED: This is only used during migration period.
        """
        try:
            from core.db.repositories.agent_group_repo import AgentGroupRepository

            groups = await AgentGroupRepository().list_all()

            for group in groups:
                user_ids = group.get("user_ids", [])
                persona_ids = group.get("persona_ids", [])

                if str(user_id) in [str(uid) for uid in user_ids] and int(
                    agent_id
                ) in [int(pid) for pid in persona_ids]:
                    logger.info(
                        f"Legacy access granted for user {user_id}, agent {agent_id}"
                    )
                    return {
                        "allowed": True,
                        "permission_level": "execute",
                        "source": "legacy",
                    }

            return {"allowed": False, "permission_level": None, "source": "legacy"}

        except Exception as e:
            logger.error(f"Legacy permission check failed: {e}")
            return {"allowed": False, "permission_level": None, "source": None}

    async def get_user_accessible_agents(self, user_id: str) -> list[str]:
        """
        Get all agent IDs that user can access.

        Returns:
            List of agent IDs (as strings)
        """
        try:
            client = await self._get_client()
            headers = {}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token

            response = await client.get(
                f"{self.user_service_url}/api/permissions/users/{user_id}/accessible-resources",
                params={"resource_type": "agent"},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            resources = data.get("resources", [])
            return [r["resource_id"] for r in resources]

        except httpx.HTTPError as e:
            logger.warning(f"Failed to get accessible agents for user {user_id}: {e}")
            # Fallback to legacy
            return await self._get_legacy_accessible_agents(user_id)
        except Exception as e:
            logger.error(f"Unexpected error getting accessible agents: {e}")
            return []

    async def _get_legacy_accessible_agents(self, user_id: str) -> list[str]:
        """
        Fallback: get agents from legacy groups.

        DEPRECATED: This is only used during migration period.
        """
        try:
            from core.db.repositories.agent_group_repo import AgentGroupRepository

            groups = await AgentGroupRepository().list_all()
            agent_ids: set[str] = set()

            for group in groups:
                user_ids = group.get("user_ids", [])
                if str(user_id) in [str(uid) for uid in user_ids]:
                    persona_ids = group.get("persona_ids", [])
                    for pid in persona_ids:
                        agent_ids.add(str(pid))

            return list(agent_ids)

        except Exception as e:
            logger.error(f"Legacy accessible agents check failed: {e}")
            return []

    async def check_bulk_access(
        self, user_id: str, agent_ids: list[str | int]
    ) -> dict[str, bool]:
        """
        Check access for multiple agents at once.

        Returns:
            Dict mapping agent_id -> allowed (bool)
        """
        results = {}
        for agent_id in agent_ids:
            access = await self.check_agent_access(user_id, agent_id)
            results[str(agent_id)] = access["allowed"]
        return results


# Singleton
_permission_service_instance: PermissionService | None = None


def get_permission_service() -> PermissionService:
    """Get singleton permission service instance."""
    global _permission_service_instance
    if _permission_service_instance is None:
        _permission_service_instance = PermissionService()
    return _permission_service_instance
