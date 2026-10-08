"""Strict, lazy Keycloak transport and attribute-backed identity records."""

import asyncio
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import quote

from config_manager import env
from error_contract import ConfigurationError, raise_for_httpx_response

PERMISSIONS = "agentic.permissions"
BUILTIN = "agentic.builtin"
PRIMARY_ROLE = "agentic.primary_role"
CATALOG_ROLE = "agentic-permission-catalog"


def segment(value):
    return quote(str(value), safe="")


def manageable(name):
    return name not in {
        "basic",
        "offline_access",
        "uma_authorization",
        CATALOG_ROLE,
    } and not name.startswith("default-roles-")


@dataclass(frozen=True, slots=True)
class CompositeRoleRecord:
    """A platform role: a manageable Keycloak realm role.

    ``id`` is Keycloak's server-generated role ID and the only identity.
    ``bundle_ids``/``bundle_names`` are its composite children on ``*-service``
    clients (feature bundles); other composites are not application data.
    """

    id: str
    name: str
    description: str | None
    permissions: tuple[str, ...]
    bundle_ids: tuple[str, ...]
    bundle_names: tuple[str, ...]
    is_builtin: bool


@dataclass(frozen=True, slots=True)
class CoarseRoleRecord:
    """A feature bundle: a Keycloak client role on a ``*-service`` client.

    ``id`` is Keycloak's server-generated role ID and the only identity; a
    ``name`` is unique only within its ``service_client``.
    """

    id: str
    name: str
    description: str | None
    service_client: str
    permissions: tuple[str, ...]
    is_builtin: bool = False


class _TTLCache:
    """Short-lived snapshot of read-only Keycloak catalog reads.

    Keycloak admin lookups are the dominant cost of the role screens, and the
    catalog changes only through writes we already observe. A few seconds of
    reuse collapses the burst of identical GETs a single page interaction makes,
    without letting an out-of-band edit go unnoticed for long.
    """

    def __init__(self, ttl: float):
        self._ttl = ttl
        self._entries: dict[Any, tuple[float, Any]] = {}
        self._locks: dict[Any, asyncio.Lock] = {}

    def clear(self) -> None:
        self._entries.clear()

    async def get(self, key, loader):
        entry = self._entries.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        async with self._locks.setdefault(key, asyncio.Lock()):
            entry = self._entries.get(key)
            if entry and entry[0] > time.monotonic():
                return entry[1]
            value = await loader()
            self._entries[key] = (time.monotonic() + self._ttl, value)
            return value


CATALOG_TTL_SECONDS = 5.0
catalog_cache = _TTLCache(CATALOG_TTL_SECONDS)


class KeycloakRoleClient:
    async def request(self, method, path, *, missing=False, **kwargs):
        role_write = method != "GET" and (
            path == "/roles"
            or path.startswith("/roles/")
            or path.startswith("/roles-by-id/")
            or (path.startswith("/clients/") and "/roles" in path)
        )
        if role_write:
            from config_manager import env
            from redis.asyncio import Redis

            from .keycloak_authorization import clear_feature_grants, policy_write_lock, reconcile

            settings = env
            async with (
                Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    password=settings.REDIS_PASSWORD,
                ) as redis,
                policy_write_lock(redis, settings.KEYCLOAK_REALM),
            ):
                await clear_feature_grants(self)
                result = await self._request(method, path, missing=missing, **kwargs)
                await reconcile(self)
                return result
        return await self._request(method, path, missing=missing, **kwargs)

    async def _request(self, method, path, *, missing=False, **kwargs):
        from src.service.keycloak_service import get_keycloak_service

        response = await get_keycloak_service()._keycloak_request(method, path, **kwargs)
        if missing and response.status_code == 404:
            return None
        raise_for_httpx_response(response)
        if method != "GET":
            invalidate_role_access()
        return response.json() if response.content else None

    async def pages(self, path, **params):
        rows = []
        while True:
            batch = await self.request("GET", path, params={**params, "first": len(rows), "max": 100})
            rows.extend(batch)
            if len(batch) < 100:
                return rows

    async def clients(self):
        managed = {
            env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID,
            env.KEYCLOAK_RAG_SERVICE_CLIENT_ID,
            env.KEYCLOAK_TOOLS_SERVICE_CLIENT_ID,
            env.KEYCLOAK_USER_SERVICE_CLIENT_ID,
        }

        async def load():
            return [c for c in await self.pages("/clients") if c["clientId"] in managed]

        return list(await catalog_cache.get(("service-clients", tuple(sorted(managed))), load))

    async def client_id(self, name):
        clients = await self.request("GET", "/clients", params={"clientId": name})
        match = next((c for c in clients if c["clientId"] == name), None)
        if not match:
            raise ConfigurationError()
        return match["id"]

    async def expanded_permissions(self, role, seen=None):
        seen = set() if seen is None else seen
        if role["id"] in seen:
            return []
        seen.add(role["id"])
        full = await self.request("GET", f"/roles-by-id/{segment(role['id'])}")
        permissions = set(full.get("attributes", {}).get(PERMISSIONS, []))
        if full["name"] == "system-admin" and not full.get("clientRole"):
            permissions.add("*")
        if full.get("composite"):
            children = await self.request("GET", f"/roles-by-id/{segment(role['id'])}/composites")
            for child in children:
                permissions.update(await self.expanded_permissions(child, seen))
        return sorted(permissions)


class DirectKeycloakRoleClient(KeycloakRoleClient):
    """Role client over an explicitly supplied Keycloak service.

    Writes go straight to the admin API, without the feature-policy lock and
    reconciliation that ``KeycloakRoleClient.request`` wraps around role writes.
    """

    def __init__(self, keycloak):
        self._keycloak = keycloak

    async def request(self, method, path, *, missing=False, **kwargs):
        response = await self._keycloak._keycloak_request(method, path, **kwargs)
        if missing and response.status_code == 404:
            return None
        raise_for_httpx_response(response)
        return response.json() if response.content else None


async def ensure_identity_user_profile(client=None):
    """Declare application metadata with administrator-only write access."""
    client = client or KeycloakRoleClient()
    profile = await client.request("GET", "/users/profile")
    names = {
        PRIMARY_ROLE,
        "agentic.team_name",
        "agentic.invited",
        "agentic.password_configured",
        "agentic.is_external_keycloak_user",
        "agentic.legacy_identity_id",
        "agenticai.memberships",
        "agenticai.primary_organization",
    }
    attributes = list(profile.get("attributes", []))
    by_name = {attribute["name"]: attribute for attribute in attributes}
    for name in sorted(names):
        attribute = dict(by_name.get(name, {"name": name, "multivalued": True}))
        attribute["permissions"] = {"view": ["admin"], "edit": ["admin"]}
        if name in by_name:
            attributes[attributes.index(by_name[name])] = attribute
        else:
            attributes.append(attribute)
    await client.request("PUT", "/users/profile", json={**profile, "attributes": attributes})


def invalidate_role_access():
    """Invalidate local authorization snapshots after authoritative grant mutations."""
    catalog_cache.clear()

    from src.service import permission_resolver_service

    resolver = permission_resolver_service._permission_resolver_service_instance
    if resolver is not None:
        resolver._cache.clear()


def primary_role_name(role_names, marker=None):
    """Choose one deterministic display role from effective assignments."""
    names = set(role_names)
    candidates = [marker] if isinstance(marker, str) else marker or []
    for name in candidates:
        if name in names:
            return name
    return next(
        (name for name in ("system-admin", "enterprise-admin", "enduser") if name in names),
        min(names) if names else "",
    )
