"""Fetch caller-visible resource catalogs through Gateway."""

from typing import Any
from urllib.parse import urlsplit

from error_contract import (
    BadRequestError,
    DependencyUnavailableError,
    ForbiddenError,
    UnauthorizedError,
    from_httpx_error,
)
import httpx
from observability import correlation_event_hooks

CatalogUnavailableError = DependencyUnavailableError


class ResourceCatalogClient:
    def __init__(self, gateway_url: str | None):
        self.gateway_url = (gateway_url or "").rstrip("/")

    async def list_resources(self, resource_type: str, access_token: str) -> list[dict[str, Any]]:
        paths = {
            "agent": "/agent-service/api/v1/persona/options",
            "rag_collection": "/rag-service/api/v1/collections",
        }
        if resource_type not in paths:
            raise BadRequestError()
        if not access_token:
            raise UnauthorizedError(message_key="errors.user_service.auth.required")
        gateway = urlsplit(self.gateway_url)
        if (
            gateway.scheme not in {"http", "https"}
            or not gateway.netloc
            or gateway.username
            or gateway.password
            or gateway.query
            or gateway.fragment
        ):
            raise CatalogUnavailableError(message_key="errors.user_service.organization.catalog_gateway_unconfigured")
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=False,
                event_hooks=correlation_event_hooks(),
            ) as client:
                response = await client.get(
                    f"{self.gateway_url}{paths[resource_type]}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if response.status_code == 401:
                raise UnauthorizedError(message_key="errors.user_service.auth.required")
            if response.status_code == 403:
                raise ForbiddenError()
            if response.status_code != 200:
                raise CatalogUnavailableError(message_key="errors.user_service.organization.catalog_unavailable")
            return self._normalize(resource_type, response.json())
        except httpx.HTTPError as error:
            raise from_httpx_error(error) from error
        except (ValueError, TypeError, KeyError) as error:
            raise CatalogUnavailableError(message_key="errors.user_service.organization.catalog_unavailable") from error

    @staticmethod
    def _normalize(resource_type: str, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise CatalogUnavailableError(message_key="errors.user_service.organization.catalog_unavailable")
        resources = []
        seen: set[str] = set()
        for row in payload:
            if not isinstance(row, dict):
                raise CatalogUnavailableError(message_key="errors.user_service.organization.catalog_unavailable")
            resource_id = row["id" if resource_type == "agent" else "uuid"]
            name = row["name"]
            if (
                isinstance(resource_id, bool)
                or not isinstance(resource_id, (str, int))
                or not str(resource_id)
                or not isinstance(name, str)
            ):
                raise CatalogUnavailableError(message_key="errors.user_service.organization.catalog_unavailable")
            resource_id = str(resource_id)
            if resource_id in seen:
                continue
            seen.add(resource_id)
            resource = {"id": resource_id, "name": name}
            if isinstance(row.get("description"), str):
                resource["description"] = row["description"]
            resources.append(resource)
        return resources
