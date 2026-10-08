"""Keycloak feature authorization policy projection shared by bootstrap and role writes."""

from contextlib import asynccontextmanager
import json
from urllib.parse import quote

try:
    from error_contract import ConfigurationError, DependencyUnavailableError
except ImportError:
    # keycloak-bootstrap loads this file on plain Python, without the web stack
    # error_contract needs. The service always has it, so it gets the typed
    # errors; the bootstrap gets plain ones that still fail the run.

    class ConfigurationError(RuntimeError):  # type: ignore[no-redef]
        pass

    class DependencyUnavailableError(RuntimeError):  # type: ignore[no-redef]
        pass


async def ensure_service_authorization(client):
    """Provision existing service resource servers under the caller's write lock."""
    for service in await client.clients():
        path = "/clients/" + quote(service["id"], safe="")
        details = await client.request("GET", path)
        if details.get("publicClient"):
            raise ConfigurationError()
        if not details.get("authorizationServicesEnabled"):
            await client.request("PUT", path, json={**details, "authorizationServicesEnabled": True})
        base = path + "/authz/resource-server"
        settings = await client.request("GET", base)
        required = {"policyEnforcementMode": "ENFORCING", "allowRemoteResourceManagement": False}
        if any(settings.get(key) != value for key, value in required.items()):
            await client.request("PUT", base, json={**settings, **required})
        # Enabling authorization creates a wildcard allow-all permission. Remove
        # it before its policy; repeat cleanup to recover interrupted provisioning.
        policies = await client.request("GET", base + "/policy", params={"max": -1})
        for name in ("Default Permission", "Default Policy"):
            for policy in policies:
                if policy["name"] == name:
                    await client.request("DELETE", base + "/policy/" + quote(policy["id"], safe=""))
        resources = await client.request("GET", base + "/resource", params={"max": -1})
        for resource in resources:
            if resource.get("name") == "Default Resource":
                await client.request("DELETE", base + "/resource/" + quote(resource["_id"], safe=""))


@asynccontextmanager
async def policy_write_lock(redis, realm):
    """Serialize policy writes without lease expiry permitting stale writers.

    A process crash leaves the lock held for explicit operator recovery. Acquisition
    is bounded; no role mutation occurs when Redis is unavailable or the lock is held.
    """
    lock = redis.lock(
        f"agentic:keycloak:{realm}:feature-policy-write",
        timeout=None,
        blocking_timeout=5,
        thread_local=False,
    )
    if not await lock.acquire():
        raise DependencyUnavailableError()
    try:
        yield
    finally:
        await lock.release()


async def clear_feature_grants(client):
    """Fail closed if a role write succeeds but policy synchronization fails."""
    for service in await client.clients():
        base = f"/clients/{quote(service['id'], safe='')}/authz/resource-server/policy"
        for policy in await client.request("GET", base, params={"max": -1}):
            if policy["name"].startswith("agentic:permission:"):
                await client.request("DELETE", base + "/" + quote(policy["id"], safe=""))


async def reconcile(client, inventory=None):
    """Project current realm/client roles into managed feature policies.

    Other resource types and their policies are preserved. Role policies fetch
    live user roles, so assignment and composite membership changes are immediate.
    """
    clients = await client.clients()
    roles = await client.pages("/roles", briefRepresentation="false")
    for service in clients:
        roles.extend(await client.pages(f"/clients/{quote(service['id'], safe='')}/roles", briefRepresentation="false"))
    by_id = {}

    async def load(role):
        if role["id"] in by_id:
            return
        full = await client.request("GET", f"/roles-by-id/{quote(role['id'], safe='')}")
        by_id[role["id"]] = full
        if full.get("composite"):
            children = await client.request("GET", f"/roles-by-id/{quote(role['id'], safe='')}/composites")
            full["children"] = [child["id"] for child in children]
            for child in children:
                await load(child)

    for role in roles:
        await load(role)
    for service in clients:
        base = f"/clients/{quote(service['id'], safe='')}/authz/resource-server"
        resources = await client.request("GET", base + "/resource", params={"max": -1})
        if inventory is not None:
            permissions = [
                permission
                for row in inventory
                if row["audience"] == service["clientId"]
                for permission in row["permissions"]
            ]
        else:
            permissions = [
                f"{resource['name']}#{scope['name']}"
                for resource in resources
                if resource.get("type") == "agentic:feature"
                for scope in resource.get("scopes", [])
            ]
        settings = authorization_settings(permissions, list(by_id.values()))
        existing_uris = {resource["name"]: resource.get("uris", []) for resource in resources}
        for resource in settings["resources"]:
            if resource["name"] in existing_uris:
                resource["uris"] = existing_uris[resource["name"]]
        existing = await client.request("GET", base + "/policy", params={"max": -1})
        wanted = {policy["name"] for policy in settings["policies"]}
        # Remove default allow-all and stale projections before installing grants.
        for policy in sorted(existing, key=lambda p: p.get("type") != "resource"):
            if policy["name"] in {"Default Policy", "Default Permission"} or (
                policy["name"].startswith(("agentic:role:", "agentic:permission:")) and policy["name"] not in wanted
            ):
                await client.request("DELETE", base + "/policy/" + quote(policy["id"], safe=""))
        # Import resources and policy dependencies before updating existing permissions.
        await client.request("POST", base + "/import", json=settings)
        existing_by_name = {policy["name"]: policy for policy in existing}
        for policy in settings["policies"]:
            previous = existing_by_name.get(policy["name"])
            if policy["type"] != "scope" or previous is None:
                continue
            # Existing scope permissions can retain old associations on import.
            # The typed update explicitly replaces resources, scopes, and role policies.
            config = policy["config"]
            await client.request(
                "PUT",
                base + "/permission/scope/" + quote(previous["id"], safe=""),
                json={
                    **{key: value for key, value in policy.items() if key != "config"},
                    "id": previous["id"],
                    "resources": json.loads(config["resources"]),
                    "scopes": json.loads(config["scopes"]),
                    "policies": json.loads(config["applyPolicies"]),
                },
            )


def authorization_settings(permissions, roles):
    by_id = {role["id"]: role for role in roles}

    def expanded(role, seen=None):
        seen = set() if seen is None else seen
        if role["id"] in seen:
            return set()
        seen.add(role["id"])
        grants = set(role.get("attributes", {}).get("agentic.permissions", []))
        if role["name"] == "system-admin" and not role.get("clientRole"):
            grants.add("*")
        for child in role.get("children", []):
            grants.update(expanded(by_id[child], seen))
        return grants

    grants = {role["id"]: expanded(role) for role in roles}
    policies = [
        {
            "name": f"agentic:role:{role['id']}",
            "type": "role",
            "logic": "POSITIVE",
            "decisionStrategy": "UNANIMOUS",
            "config": {
                "roles": json.dumps([{"id": role["id"], "required": False}]),
                "fetchRoles": "true",
            },
        }
        for role in roles
    ]
    resources = {}
    scopes = set()
    for permission in sorted(set(permissions)):
        resource, scope = permission.split("#", 1)
        scopes.add(scope)
        resources.setdefault(resource, set()).add(scope)
        allowed = [
            f"agentic:role:{role_id}"
            for role_id, values in grants.items()
            if "*" in values or f"{resource}:{scope}" in values
        ]
        # No permission is created when no role grants it: Keycloak denies by default.
        if allowed:
            policies.append(
                {
                    "name": f"agentic:permission:{permission}",
                    "type": "scope",
                    "logic": "POSITIVE",
                    "decisionStrategy": "AFFIRMATIVE",
                    "config": {
                        "resources": json.dumps([resource]),
                        "scopes": json.dumps([scope]),
                        "applyPolicies": json.dumps(allowed),
                    },
                }
            )
    return {
        "allowRemoteResourceManagement": False,
        "policyEnforcementMode": "ENFORCING",
        "decisionStrategy": "AFFIRMATIVE",
        "resources": [
            {
                "name": resource,
                "type": "agentic:feature",
                "ownerManagedAccess": False,
                "scopes": [{"name": scope} for scope in sorted(values)],
            }
            for resource, values in sorted(resources.items())
        ],
        "scopes": [{"name": scope} for scope in sorted(scopes)],
        "policies": policies,
    }
