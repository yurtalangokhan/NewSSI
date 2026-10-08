"""
Permission checking service for agent-service.

Replaces legacy agent_groups with new organization-based permission system
by delegating to user-service.
"""

from typing import Any

from config_manager import env
from error_contract import (
    DependencyResponseError,
    from_httpx_error,
)
import httpx
from localization import get_locale

from core.http import outbound
from core.http.api_versioning import USER_SERVICE_API_PREFIX
from core.observability.logger import get_logger
from integrations.user_response import read_user_response

logger = get_logger(__name__)

# Permission checks sit on the request path; a slow user-service must not hold
# the caller any longer than the old per-instance client's 5s budget.
_PERMISSION_HTTP_TIMEOUT_SECONDS = 5.0


class PermissionService:
    """Check resource permissions via user-service."""

    def __init__(self):
        self.user_service_url = env.INTERNAL_USER_SERVICE_URL
        self.internal_token = env.INTERNAL_SERVICE_TOKEN
        self._timeout_seconds = _PERMISSION_HTTP_TIMEOUT_SECONDS

    async def close(self):
        """No-op: the shared client is owned by the transport, not by this service.

        Kept so existing callers that shut a ``PermissionService`` down keep
        working; closing the shared client here would break every other user of
        the user-service transport.
        """
        return None

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
                "source": "user" | "organization" | "inherited" | "public"
            }
        """
        try:
            headers = {"X-Language": get_locale()}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token

            response = await outbound.request(
                outbound.USER_SERVICE,
                "POST",
                f"{self.user_service_url}{USER_SERVICE_API_PREFIX}/permissions/check",
                timeout=self._timeout_seconds,
                json={
                    "user_id": str(user_id),
                    "resource_type": "agent",
                    "resource_id": str(agent_id),
                    "required_permission": required_permission,
                },
                headers=headers,
            )
            data = read_user_response(response)
            if not isinstance(data, dict) or not isinstance(data.get("allowed"), bool):
                raise ValueError("Invalid permission response")
            return data

        except httpx.HTTPError as exc:
            raise from_httpx_error(exc) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise DependencyResponseError() from exc

    async def get_user_accessible_agents(self, user_id: str, required_permission: str = "execute") -> list[str]:
        """
        Get all agent IDs that user can access.

        Returns:
            List of agent IDs (as strings)
        """
        try:
            headers = {"X-Language": get_locale()}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token

            response = await outbound.request(
                outbound.USER_SERVICE,
                "GET",
                f"{self.user_service_url}{USER_SERVICE_API_PREFIX}/permissions/users/{user_id}/accessible-resources",
                timeout=self._timeout_seconds,
                params={"resource_type": "agent", "required_permission": required_permission},
                headers=headers,
            )
            data = read_user_response(response)
            if not isinstance(data, dict) or not isinstance(data.get("resources", []), list):
                raise DependencyResponseError()
            resources = data.get("resources", [])
            if any(not isinstance(r, dict) or "resource_id" not in r for r in resources):
                raise DependencyResponseError()
            return [r["resource_id"] for r in resources]

        except httpx.HTTPError as exc:
            raise from_httpx_error(exc) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise DependencyResponseError() from exc

    async def check_bulk_access(self, user_id: str, agent_ids: list[str | int]) -> dict[str, bool]:
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
