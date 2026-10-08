"""Small async admin client for Keycloak organization adapters."""

from urllib.parse import urlencode

from error_contract import DependencyResponseError, raise_for_httpx_response

from src.core.exceptions import ConflictError


class KeycloakGroupClient:
    def __init__(self, keycloak=None):
        if keycloak is None:
            from src.service.keycloak_service import get_keycloak_service

            keycloak = get_keycloak_service()
        self.keycloak = keycloak

    async def request(self, method, path, **kwargs):
        response = await self.keycloak._keycloak_request(method, path, **kwargs)
        if response.status_code == 404:
            return None
        if response.status_code == 409:
            raise ConflictError(message_key="errors.user_service.keycloak.identity_already_exists")
        raise_for_httpx_response(response)
        if method != "GET":
            from .keycloak_role_client import invalidate_role_access

            invalidate_role_access()
        return response

    async def get(self, path):
        response = await self.request("GET", path)
        return response.json() if response is not None else None

    async def pages(self, path):
        result = []
        first = 0
        while True:
            params = urlencode({"first": first, "max": 100, "briefRepresentation": "false"})
            page = await self.get(f"{path}?{params}")
            if page is None:
                return result
            if not isinstance(page, list):
                raise DependencyResponseError()
            result.extend(page)
            if len(page) < 100:
                return result
            first += len(page)
