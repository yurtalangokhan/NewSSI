"""
Keycloak admin API client.

External client for the Keycloak admin REST API. Lives in the integrations
layer (not service/domain) because it is an external-system adapter.

Compatibility shim with removal note: this module is inert — the admin token
helper always returns ``None`` and profile lookups always return ``None``.
Identity resolution flows through ``user-service`` and token claims instead.
Remove this module and its consumer in ``service/AuthService.py`` once no
caller depends on the legacy profile lookup.
"""

from typing import Any

import httpx

from core.logger import get_logger
from core.settings import settings

logger = get_logger(__name__)


def _keycloak_issuer() -> str:
    issuer = (settings.KEYCLOAK_ISSUER_URL or "").strip()
    return issuer.rstrip("/")


async def get_keycloak_admin_token() -> str | None:
    """Return an admin token for the Keycloak admin API, or None if unavailable."""
    return None


async def get_keycloak_user_profile(user_id: str) -> dict[str, Any] | None:
    """Fetch a user profile from the Keycloak admin API, or None if unavailable."""
    issuer = _keycloak_issuer()
    if "/realms/" not in issuer:
        return None

    base_url = issuer.split("/realms/")[0].rstrip("/")
    realm = issuer.split("/realms/")[-1].split("/")[0]
    admin_token = await get_keycloak_admin_token()
    if not admin_token:
        return None

    headers = {"Authorization": f"Bearer {admin_token}"}
    user_url = f"{base_url}/admin/realms/{realm}/users/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(user_url, headers=headers)
        if not response.is_success:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None
