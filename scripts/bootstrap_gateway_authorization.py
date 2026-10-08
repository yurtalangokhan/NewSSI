#!/usr/bin/env python3
"""Reconcile Keycloak resources, scopes, role policies, and gateway login claims."""

import asyncio
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from gateway_authorization import _shared, inventory, reconcile

# The realm roles the gateway reads from a login token (``realm_access.roles``): the two
# administrator roles decide the primary role, ``enduser`` is the default. Every other grant is
# evaluated by the authorization services from the user model, not from the token.
PLATFORM_REALM_ROLES = ("system-admin", "enterprise-admin", "enduser")


class AdminClient:
    def __init__(self):
        self.base = os.environ["KEYCLOAK_BASE_URL"].rstrip("/")
        self.realm = os.environ["KEYCLOAK_REALM"]
        self.token = os.environ.get("KEYCLOAK_BOOTSTRAP_ADMIN_TOKEN")

    def refresh_token(self):
        realm = quote(os.environ.get("KEYCLOAK_ADMIN_REALM", "master"), safe="")
        request = Request(
            self.base + f"/realms/{realm}/protocol/openid-connect/token",
            data=urlencode(
                {
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": os.environ["KEYCLOAK_ADMIN"],
                    "password": os.environ["KEYCLOAK_ADMIN_PASSWORD"],
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            self.token = json.load(response)["access_token"]

    async def request(self, method, path, **kwargs):
        def send():
            if not self.token:
                self.refresh_token()
            url = self.base + "/admin/realms/" + quote(self.realm, safe="") + path
            if kwargs.get("params"):
                url += "?" + urlencode(kwargs["params"])
            payload = json.dumps(kwargs["json"]).encode() if "json" in kwargs else None
            request = Request(
                url,
                data=payload,
                method=method,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Content-Type": "application/json",
                },
            )
            try:
                response = urlopen(request, timeout=30)
            except HTTPError as error:
                if error.code != 401:
                    raise
                self.refresh_token()
                request.add_header("Authorization", "Bearer " + self.token)
                response = urlopen(request, timeout=30)
            with response:
                body = response.read()
                return json.loads(body) if body else None

        return await asyncio.to_thread(send)

    async def pages(self, path, **params):
        rows = []
        while True:
            page = await self.request(
                "GET", path, params={**params, "first": len(rows), "max": 100}
            )
            rows.extend(page)
            if len(page) < 100:
                return rows

    async def clients(self):
        managed = {
            os.environ[f"KEYCLOAK_{service}_SERVICE_CLIENT_ID"]
            for service in ("USER", "AGENT", "RAG", "TOOLS")
        }
        return [
            client
            for client in await self.pages("/clients")
            if client["clientId"] in managed
        ]


async def reconcile_login_scope(client, login_client_id):
    """Map exactly the existing platform realm roles into the login client's tokens."""
    path = "/clients/" + quote(login_client_id, safe="") + "/scope-mappings/realm"
    wanted = {
        role["name"]: role
        for role in await client.pages("/roles")
        if role["name"] in PLATFORM_REALM_ROLES
    }
    current = {role["name"]: role for role in await client.request("GET", path)}
    missing = [
        wanted[name]
        for name in PLATFORM_REALM_ROLES
        if name in wanted and name not in current
    ]
    stale = [role for name, role in current.items() if name not in wanted]
    if missing:
        await client.request("POST", path, json=missing)
    if stale:
        await client.request("DELETE", path, json=stale)


async def bootstrap(client):
    gateway_id = os.environ["GATEWAY_KEYCLOAK_CLIENT_ID"]
    secret = os.environ.get("GATEWAY_KEYCLOAK_CLIENT_SECRET")
    if not secret:
        raise ValueError("GATEWAY_KEYCLOAK_CLIENT_SECRET must be explicitly configured")
    existing = await client.request("GET", "/clients", params={"clientId": gateway_id})
    payload = {
        "clientId": gateway_id,
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "secret": secret,
    }
    if existing:
        await client.request(
            "PUT", "/clients/" + quote(existing[0]["id"], safe=""), json=payload
        )
    else:
        await client.request("POST", "/clients", json=payload)
    for service in await client.clients():
        await client.request(
            "PUT",
            "/clients/" + quote(service["id"], safe=""),
            json={
                **service,
                "authorizationServicesEnabled": True,
                "serviceAccountsEnabled": True,
                "publicClient": False,
            },
        )
    login_id = os.environ["KEYCLOAK_CLIENT_ID"]
    login = await client.request("GET", "/clients", params={"clientId": login_id})
    if len(login) != 1:
        raise ValueError("Expected exactly one configured frontend client")
    # "Full scope allowed" (deprecated in Keycloak 26) would copy every role of the user into
    # the token; the login client maps exactly the platform roles instead.
    await client.request(
        "PUT",
        "/clients/" + quote(login[0]["id"], safe=""),
        json={**login[0], "fullScopeAllowed": False},
    )
    await reconcile_login_scope(client, login[0]["id"])
    base = "/clients/" + quote(login[0]["id"], safe="") + "/protocol-mappers/models"
    desired = [
        {
            "name": "agentic-gateway-audience",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.client.audience": gateway_id,
                "access.token.claim": "true",
                "id.token.claim": "false",
                "introspection.token.claim": "true",
            },
        },
        {
            "name": "agentic-gateway-groups",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-group-membership-mapper",
            "config": {
                "claim.name": "groups",
                "full.path": "true",
                "access.token.claim": "true",
                "id.token.claim": "false",
                "introspection.token.claim": "true",
                "userinfo.token.claim": "true",
            },
        },
        {
            "name": "agentic-primary-role",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": "agentic.primary_role",
                "claim.name": "primary_role",
                "jsonType.label": "String",
                "multivalued": "false",
                "access.token.claim": "true",
                "introspection.token.claim": "true",
                "userinfo.token.claim": "true",
                "id.token.claim": "false",
            },
        },
    ]
    targets = [login[0], *await client.clients()]
    for target in targets:
        base = "/clients/" + quote(target["id"], safe="") + "/protocol-mappers/models"
        mappers = await client.request("GET", base)
        for mapper in desired if target["id"] == login[0]["id"] else desired[:1]:
            previous = next(
                (row for row in mappers if row["name"] == mapper["name"]), None
            )
            await client.request(
                "PUT" if previous else "POST",
                base + ("/" + quote(previous["id"], safe="") if previous else ""),
                json={**mapper, **({"id": previous["id"]} if previous else {})},
            )
    await reconcile(client, inventory(Path(__file__).resolve().parents[1]))


async def main():
    from redis.asyncio import Redis

    client = AdminClient()
    async with (
        Redis(
            host=os.environ.get("REDIS_HOST", "redis"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            db=int(os.environ.get("REDIS_DB", "0")),
            password=os.environ.get("REDIS_PASSWORD") or None,
        ) as redis,
        _shared.policy_write_lock(redis, client.realm),
    ):
        await bootstrap(client)


if __name__ == "__main__":
    asyncio.run(main())
    print("[ok] Gateway Keycloak authorization reconciled")
