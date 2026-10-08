"""Connection reuse for explicitly scoped administrative migration jobs."""

import httpx
from observability import correlation_event_hooks


class KeycloakAdminSession:
    def __init__(self, keycloak):
        self.keycloak = keycloak
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(600, connect=15),
            event_hooks=correlation_event_hooks(),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def _keycloak_request(self, method, path, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {await self.keycloak._get_admin_token()}"
        url = f"{self.keycloak.get_base_url()}/admin/realms/{self.keycloak.get_realm()}{path}"
        return await self.client.request(method, url, headers=headers, **kwargs)
