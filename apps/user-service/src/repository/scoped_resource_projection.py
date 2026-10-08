"""Incremental, fail-closed projection for organization workspace saves."""

from urllib.parse import quote

from config_manager import env
from error_contract import DependencyResponseError

from .keycloak_resource_authorization import (
    INSTANCE_POLICY_PREFIX,
    PERMISSION_LEVELS,
    instance_authorization_objects,
    resource_clients,
)


class ScopedResourceProjection:
    def __init__(self, projection, redis):
        self.projection = projection
        self.client = projection.client
        self.redis = redis

    async def run(self, mutation, target_type, target_id, resource_type, desired_resource_ids):
        # The caller holds the shared policy lock, including old-state discovery.
        realm = quote(env.KEYCLOAK_REALM, safe="")
        journal = f"agentic:keycloak:{realm}:resource-projection:{resource_type}:{target_type}:{target_id}"
        pending = await self.redis.smembers(journal)
        affected = {value.decode() if isinstance(value, bytes) else value for value in pending}
        affected.update(desired_resource_ids)
        affected.update(await self.projection._target_resource_ids(target_type, target_id, resource_type))
        if not affected:
            return await mutation()
        # No expiry: removals must remain recoverable after SQL has committed.
        await self.redis.sadd(journal, *sorted(affected))
        client_id = await self.client.client_id(resource_clients()[resource_type])
        base = f"/clients/{quote(client_id, safe='')}/authz/resource-server"
        await self._clear_permissions(base, resource_type, affected)
        result = await mutation()
        inventory = await self.projection.inventory(resource_type, affected)
        await self._reconcile(base, instance_authorization_objects(inventory, resource_type))
        await self.redis.delete(journal)
        return result

    async def _clear_permissions(self, base, resource_type, affected):
        for resource_id in sorted(affected):
            prefix = f"{INSTANCE_POLICY_PREFIX}permission:{resource_type}:{resource_id}#"
            names = {prefix + level for level in PERMISSION_LEVELS}
            policies = await self.client.request(
                "GET", base + "/policy", params={"name": prefix, "max": -1, "permission": True}
            )
            for policy in policies:
                if policy["name"] in names:
                    await self.client.request("DELETE", base + "/policy/" + quote(policy["id"], safe=""))

    async def _ensure_object(self, base, kind, value):
        bucket = "resource" if kind == "resource" else "policy"
        matches = await self.client.request("GET", base + f"/{bucket}", params={"name": value["name"], "max": -1})
        exact = [item for item in matches if item["name"] == value["name"]]
        if len(exact) > 1:
            raise DependencyResponseError()
        if exact:
            item = exact[0]
            if item.get("type") != value["type"]:
                raise DependencyResponseError()
        else:
            item = await self.client.request("POST", base + f"/{kind}", json=value)
        identity = (item or {}).get("_id" if bucket == "resource" else "id")
        if not identity:
            raise DependencyResponseError()
        return identity

    async def _reconcile(self, base, objects):
        resource_ids, policy_ids = {}, {}
        for resource in objects["resources"]:
            resource_ids[resource["name"]] = await self._ensure_object(base, "resource", resource)
        for policy in objects["policies"]:
            policy_ids[policy["name"]] = await self._ensure_object(base, f"policy/{policy['type']}", policy)
        for permission in objects["permissions"]:
            await self.client.request(
                "POST",
                base + "/permission/scope",
                json={
                    **permission,
                    "resources": [resource_ids[name] for name in permission["resources"]],
                    "policies": [policy_ids[name] for name in permission["policies"]],
                },
            )
