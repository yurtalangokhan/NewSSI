"""Provision URI resources and role policies for the legacy agenticai-v1 realm."""

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from config_manager import env

from src.repository.keycloak_authorization import authorization_settings


def configured_service_clients() -> dict[str, str]:
    return {
        "agent-service": env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID,
        "rag-service": env.KEYCLOAK_RAG_SERVICE_CLIENT_ID,
        "tools-service": env.KEYCLOAK_TOOLS_SERVICE_CLIENT_ID,
        "user-service": env.KEYCLOAK_USER_SERVICE_CLIENT_ID,
    }


def route_uris(pattern: str) -> list[str]:
    """Convert the gateway's bounded path regex subset to Keycloak URI templates."""
    if not pattern.startswith("^/") or not pattern.endswith("$"):
        raise ValueError(f"unsupported gateway route: {pattern}")
    body = pattern[1:-1]
    optional_slash = body.endswith("/?")
    if optional_slash:
        body = body[:-2]
    trailing_wildcard = body.endswith("/.+")
    if trailing_wildcard:
        body = body[:-3] + "/*"
    count = 0

    def parameter(_match):
        nonlocal count
        result = f"{{p{count}}}"
        count += 1
        return result

    body = re.sub(r"\[\^/\]\+", parameter, body)
    if re.search(r"[\\^$?+()|\[\]]", body):
        raise ValueError(f"unsupported gateway route: {pattern}")
    if "*" in body and not trailing_wildcard:
        raise ValueError(f"unsupported gateway route: {pattern}")
    without_parameters = body
    for index in range(count):
        without_parameters = without_parameters.replace(f"{{p{index}}}", "")
    if "{" in without_parameters or "}" in without_parameters:
        raise ValueError(f"unsupported gateway route: {pattern}")
    if trailing_wildcard:
        return [body]
    return [body, body + "/"] if optional_slash else [body]


def project_gateway(
    rows: list[dict], service_clients: dict[str, str] | None = None
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Group protected routes into one named resource per service and entity."""
    service_clients = service_clients or configured_service_clients()
    projected: dict[str, dict[str, dict[str, set[str]]]] = {
        client: {} for client in service_clients.values()
    }
    for row in rows:
        audience = row["audience"]
        logical_service = next(
            (logical for logical, client_id in service_clients.items()
             if audience in {logical, client_id}),
            None,
        )
        if logical_service is None:
            raise ValueError(f"unknown audience: {audience}")
        uris = route_uris(row["path"])
        if not all(
            uri.startswith((f"/{logical_service}/", f"/internal/{logical_service}/"))
            for uri in uris
        ):
            raise ValueError(f"route does not match audience: {row['path']}")
        permissions = row.get("permissions", [])
        if not permissions and not row.get("authenticated_only"):
            raise ValueError(
                f"route is neither permission-protected nor authenticated-only: {row['path']}"
            )
        targets = [tuple(permission.split("#", 1)) for permission in permissions]
        if any(len(target) != 2 or not all(target) for target in targets):
            raise ValueError(f"invalid permission on route: {row['path']}")
        if not targets:
            targets = [("agentic:authenticated", None)]
        resources = projected[service_clients[logical_service]]
        for name, scope in targets:
            resource = resources.setdefault(name, {"uris": set(), "scopes": set()})
            resource["uris"].update(uris)
            if scope:
                resource["scopes"].add(scope)
    return {
        client: {
            name: {key: sorted(values) for key, values in sorted(resource.items())}
            for name, resource in sorted(resources.items())
        }
        for client, resources in projected.items()
    }


def projection_settings(resources: dict, roles: list[dict]) -> dict:
    permissions = [
        f"{name}#{scope}" for name, resource in resources.items() for scope in resource["scopes"]
    ]
    settings = authorization_settings(permissions, roles)
    by_name = {resource["name"]: resource for resource in settings["resources"]}
    for name, resource in resources.items():
        if name not in by_name:
            by_name[name] = {
                "name": name,
                "type": "agentic:feature",
                "ownerManagedAccess": False,
                "scopes": [],
            }
        by_name[name]["uris"] = resource["uris"]
    settings["resources"] = [by_name[name] for name in sorted(by_name)]
    return settings


def check_existing(resources: list[dict], policies: list[dict]) -> bool:
    """Accept defaults or previously managed objects, refusing unrelated state."""
    unknown_resources = [
        item["name"]
        for item in resources
        if item["name"] != "Default Resource" and item.get("type") != "agentic:feature"
    ]
    unknown_policies = [
        item["name"]
        for item in policies
        if item["name"] not in {"Default Permission", "Default Policy"}
        and not item["name"].startswith(("agentic:role:", "agentic:permission:"))
    ]
    if unknown_resources or unknown_policies:
        raise ValueError(
            f"unmanaged Keycloak authorization objects: "
            f"resources={unknown_resources}, policies={unknown_policies}"
        )
    return True


async def sync_existing_scope_permissions(admin, base: str, previous: list[dict], desired: list[dict]):
    """Replace associations that Keycloak's import keeps on existing scopes."""
    by_name = {policy["name"]: policy for policy in previous}
    for policy in desired:
        if policy["type"] != "scope" or policy["name"] not in by_name:
            continue
        config = policy["config"]
        await admin.request(
            "PUT",
            base + "/permission/scope/" + quote(by_name[policy["name"]]["id"], safe=""),
            json={
                **{key: value for key, value in policy.items() if key != "config"},
                "id": by_name[policy["name"]]["id"],
                "resources": json.loads(config["resources"]),
                "scopes": json.loads(config["scopes"]),
                "policies": json.loads(config["applyPolicies"]),
            },
        )


async def verify_scope_policy_links(admin, base: str, current: list[dict], desired: list[dict]):
    """Read actual Keycloak policy links, not just scope-permission names."""
    by_name = {policy["name"]: policy for policy in current}
    for policy in desired:
        if policy["type"] != "scope":
            continue
        actual = by_name.get(policy["name"])
        if not actual:
            raise RuntimeError(f"missing grant policy: {policy['name']}")
        links = await admin.request(
            "GET",
            base + "/policy/" + quote(actual["id"], safe="") + "/associatedPolicies",
        )
        actual_names = {link["name"] for link in links}
        expected_names = set(json.loads(policy["config"]["applyPolicies"]))
        if actual_names != expected_names:
            raise RuntimeError(f"stale scope policy associations: {policy['name']}")


class RealmAdmin:
    """Small transport using the configured Keycloak realm."""

    def __init__(self, base_url: str, token: str, realm: str):
        self.root = f"{base_url}/admin/realms/{quote(realm, safe='')}"
        self.http = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30)

    async def close(self):
        await self.http.aclose()

    async def request(self, method: str, path: str, **kwargs):
        response = await self.http.request(method, self.root + path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    async def pages(self, path: str, **params):
        result = []
        while True:
            batch = await self.request(
                "GET", path, params={**params, "first": len(result), "max": 100}
            )
            result.extend(batch)
            if len(batch) < 100:
                return result


async def live_roles(admin: RealmAdmin, clients: list[dict]) -> list[dict]:
    roles = await admin.pages("/roles", briefRepresentation="false")
    for client in clients:
        roles.extend(
            await admin.pages(
                f"/clients/{quote(client['id'], safe='')}/roles", briefRepresentation="false"
            )
        )
    by_id = {role["id"]: role for role in roles}
    for role in roles:
        if role.get("composite"):
            children = await admin.request(
                "GET", f"/roles-by-id/{quote(role['id'], safe='')}/composites"
            )
            role["children"] = [child["id"] for child in children]
            if any(child not in by_id for child in role["children"]):
                raise ValueError(f"unlisted composite child for {role['name']}")
    return roles


async def provision(apply: bool) -> None:
    from src.service.keycloak_service import KeycloakService

    root = Path(__file__).resolve().parents[3]
    gateway_rows = json.loads((root / "configs/apisix/gateway-policies.json").read_text())
    service_clients = configured_service_clients()
    projection = project_gateway(gateway_rows, service_clients)
    service = KeycloakService()
    realm = env.KEYCLOAK_REALM
    admin = RealmAdmin(service.get_base_url(), await service._get_admin_token(), realm)
    try:
        all_clients = await admin.pages("/clients")
        clients = {item["clientId"]: item for item in all_clients}
        missing = set(service_clients.values()) - clients.keys()
        if missing:
            raise ValueError(f"missing {realm} service clients: {sorted(missing)}")
        roles = await live_roles(admin, all_clients)
        plans = []
        for name in sorted(service_clients.values()):
            client = clients[name]
            path = f"/clients/{quote(client['id'], safe='')}"
            details = await admin.request("GET", path)
            if details.get("publicClient") or not details.get("authorizationServicesEnabled"):
                raise ValueError(f"{name} must be confidential with Authorization enabled")
            base = path + "/authz/resource-server"
            settings = await admin.request("GET", base)
            resources = await admin.request("GET", base + "/resource", params={"max": -1})
            policies = await admin.request("GET", base + "/policy", params={"max": -1})
            scopes = await admin.request("GET", base + "/scope", params={"max": -1})
            check_existing(resources, policies)
            wanted = projection_settings(projection[name], roles)
            plans.append((name, base, details, settings, resources, policies, scopes, wanted))
            print(
                f"{name}: {len(wanted['resources'])} resources, "
                f"{sum(len(r['uris']) for r in wanted['resources'])} URIs, "
                f"{len(wanted['scopes'])} scopes, "
                f"{sum(p['type'] == 'scope' for p in wanted['policies'])} grant policies"
            )
        if not apply:
            print(f"Dry run only. Use --apply to provision {realm}.")
            return
        backup_dir = (
            root
            / ".tmp/authorization-resources/backups"
            / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        backup_dir.mkdir(parents=True, exist_ok=False)
        for name, _base, details, settings, resources, policies, scopes, _ in plans:
            backup = {
                "client": details,
                "settings": settings,
                "resources": resources,
                "policies": policies,
                "scopes": scopes,
            }
            (backup_dir / f"{name}.json").write_text(json.dumps(backup, indent=2), encoding="utf-8")
        print(f"Backed up all four resource servers to {backup_dir}")
        for name, base, _, settings, resources, policies, _, wanted in plans:
            await admin.request(
                "PUT",
                base,
                json={
                    **settings,
                    "policyEnforcementMode": "ENFORCING",
                    "allowRemoteResourceManagement": False,
                },
            )
            for default_name in ("Default Permission", "Default Policy"):
                for policy in policies:
                    if policy["name"] == default_name:
                        await admin.request(
                            "DELETE", base + "/policy/" + quote(policy["id"], safe="")
                        )
            for resource in resources:
                if resource["name"] == "Default Resource":
                    await admin.request(
                        "DELETE", base + "/resource/" + quote(resource["_id"], safe="")
                    )
            await admin.request("POST", base + "/import", json=wanted)
            await sync_existing_scope_permissions(admin, base, policies, wanted["policies"])
            actual = await admin.request("GET", base + "/resource", params={"max": -1})
            actual_by_name = {item["name"]: item for item in actual}
            for desired in wanted["resources"]:
                item = actual_by_name.get(desired["name"])
                if item is None or set(item.get("uris", [])) != set(desired["uris"]):
                    raise RuntimeError(f"{name}: URI verification failed for {desired['name']}")
                actual_scopes = {scope["name"] for scope in item.get("scopes", [])}
                expected_scopes = {scope["name"] for scope in desired["scopes"]}
                if actual_scopes != expected_scopes:
                    raise RuntimeError(f"{name}: scope verification failed for {desired['name']}")
            if "Default Resource" in actual_by_name:
                raise RuntimeError(f"{name}: Default Resource remains")
            current_policies = await admin.request("GET", base + "/policy", params={"max": -1})
            policy_names = {item["name"] for item in current_policies}
            if {"Default Permission", "Default Policy"} & policy_names:
                raise RuntimeError(f"{name}: default allow policy remains")
            expected_grants = {
                item["name"] for item in wanted["policies"] if item["type"] == "scope"
            }
            if not expected_grants <= policy_names:
                raise RuntimeError(
                    f"{name}: missing grant policies: {sorted(expected_grants - policy_names)}"
                )
            await verify_scope_policy_links(admin, base, current_policies, wanted["policies"])
            current_settings = await admin.request("GET", base)
            if current_settings.get("policyEnforcementMode") != "ENFORCING":
                raise RuntimeError(f"{name}: enforcement mode is not ENFORCING")
            print(f"Verified {name}")
    finally:
        await admin.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the configured realm")
    args = parser.parse_args()
    asyncio.run(provision(args.apply))


if __name__ == "__main__":
    main()
