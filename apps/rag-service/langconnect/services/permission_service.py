"""
Permission checking service for rag-service (LangConnect).

Delegates resource permission checks to user-service.
"""

import httpx
import logging
from typing import Any

from langconnect import config

logger = logging.getLogger(__name__)


class PermissionService:
    """Check RAG collection permissions via user-service."""

    def __init__(self):
        self.user_service_url = config.USER_SERVICE_URL.rstrip("/")
        self.internal_token = getattr(config, "INTERNAL_SERVICE_TOKEN", None)
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

    async def check_collection_access(
        self,
        user_id: str,
        collection_id: str,
        required_permission: str = "read",
    ) -> dict[str, Any]:
        """
        Check if user can access a RAG collection.

        Args:
            user_id: User UUID or Keycloak ID
            collection_id: Collection UUID
            required_permission: "owner", "admin", "write", "read"

        Returns:
            {
                "allowed": bool,
                "permission_level": str | None,
                "source": "user" | "organization" | "inherited" | "public"
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
                    "resource_type": "rag_collection",
                    "resource_id": str(collection_id),
                    "required_permission": required_permission,
                },
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.warning(
                f"Permission check failed for user {user_id}, collection {collection_id}: {e}"
            )
            # Fail-safe: deny access if permission system is down
            return {
                "allowed": False,
                "permission_level": None,
                "source": None,
            }
        except Exception as e:
            logger.error(f"Unexpected error in permission check: {e}")
            return {
                "allowed": False,
                "permission_level": None,
                "source": None,
            }

    async def check_connector_access(
        self,
        user_id: str,
        connector_id: str,
        required_permission: str = "read",
    ) -> dict[str, Any]:
        """
        Check if user can access a connector.

        Args:
            user_id: User UUID or Keycloak ID
            connector_id: Connector UUID
            required_permission: "owner", "admin", "write", "read"

        Returns:
            {
                "allowed": bool,
                "permission_level": str | None,
                "source": "user" | "organization" | "inherited" | "public"
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
                    "resource_type": "connector",
                    "resource_id": str(connector_id),
                    "required_permission": required_permission,
                },
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.warning(
                f"Permission check failed for user {user_id}, connector {connector_id}: {e}"
            )
            return {
                "allowed": False,
                "permission_level": None,
                "source": None,
            }
        except Exception as e:
            logger.error(f"Unexpected error in permission check: {e}")
            return {
                "allowed": False,
                "permission_level": None,
                "source": None,
            }

    async def get_user_accessible_collections(self, user_id: str) -> list[str]:
        """
        Get all collection IDs that user can access.

        Returns:
            List of collection UUIDs (as strings)
        """
        try:
            client = await self._get_client()
            headers = {}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token

            response = await client.get(
                f"{self.user_service_url}/api/permissions/users/{user_id}/accessible-resources",
                params={"resource_type": "rag_collection"},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            resources = data.get("resources", [])
            return [r["resource_id"] for r in resources]

        except httpx.HTTPError as e:
            logger.warning(f"Failed to get accessible collections for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting accessible collections: {e}")
            return []

    async def get_user_accessible_connectors(self, user_id: str) -> list[str]:
        """
        Get all connector IDs that user can access.

        Returns:
            List of connector UUIDs (as strings)
        """
        try:
            client = await self._get_client()
            headers = {}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token

            response = await client.get(
                f"{self.user_service_url}/api/permissions/users/{user_id}/accessible-resources",
                params={"resource_type": "connector"},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            resources = data.get("resources", [])
            return [r["resource_id"] for r in resources]

        except httpx.HTTPError as e:
            logger.warning(f"Failed to get accessible connectors for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting accessible connectors: {e}")
            return []


# Singleton
_permission_service_instance: PermissionService | None = None


def get_permission_service() -> PermissionService:
    """Get singleton permission service instance."""
    global _permission_service_instance
    if _permission_service_instance is None:
        _permission_service_instance = PermissionService()
    return _permission_service_instance
