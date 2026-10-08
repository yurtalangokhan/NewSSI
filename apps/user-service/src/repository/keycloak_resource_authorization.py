"""Project SQL resource assignments into Keycloak Authorization Services."""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar
from urllib.parse import quote

from config_manager import env
from error_contract import BadRequestError, ConfigurationError
from sqlalchemy import select

from src.core.database.models import ResourcePermissionModel

from .base_repository import BaseRepository
from .keycloak_authorization import ensure_service_authorization, policy_write_lock
from .keycloak_role_client import KeycloakRoleClient

INSTANCE_POLICY_PREFIX = "agentic:instance:"
PERMISSION_LEVELS = {"owner": 100, "admin": 80, "write": 60, "read": 40, "execute": 20}
T = TypeVar("T")


def resource_clients() -> dict[str, str]:
    return {
        "agent": env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID,
        "rag_collection": env.KEYCLOAK_RAG_SERVICE_CLIENT_ID,
    }


async def project_resource_permission_mutation(mutation: Callable[[], Awaitable[T]]) -> T:
    """Apply cleanup writes through the same fail-closed projection boundary."""
    return await ResourceAuthorizationProjectionRepository().project_mutation(mutation)


def instance_authorization_objects(
    inventory: list[dict[str, Any]], resource_type: str
) -> dict[str, list[dict[str, Any]]]:
    """Build deterministic resources, exact-subject policies, and scope permissions."""
    rows = [row for row in inventory if row["resource_type"] == resource_type]
    subjects: dict[tuple[str, str], str] = {}
    resources: dict[str, list[dict[str, Any]]] = {}
    permission_subjects: dict[tuple[str, str], set[str]] = {}
    ordered_levels = sorted(PERMISSION_LEVELS)

    for row in rows:
        resource_name = f"{resource_type}:{row['resource_id']}"
        resources[resource_name] = [{"name": level} for level in ordered_levels]
        if row.get("user_id"):
            kind, subject_id = "user", str(row["user_id"])
        else:
            kind, subject_id = "group", str(row["organization_id"])
        policy_name = f"{INSTANCE_POLICY_PREFIX}{kind}:{subject_id}"
        subjects[(kind, subject_id)] = policy_name
        granted_score = PERMISSION_LEVELS[row["permission_level"]]
        for level, score in PERMISSION_LEVELS.items():
            if score <= granted_score:
                permission_subjects.setdefault((resource_name, level), set()).add(policy_name)

    policies = []
    for (kind, subject_id), name in sorted(subjects.items()):
        policy = {
            "name": name,
            "type": kind,
            "logic": "POSITIVE",
            "decisionStrategy": "UNANIMOUS",
        }
        if kind == "user":
            policy["users"] = [subject_id]
        else:
            policy["groups"] = [{"id": subject_id, "extendChildren": False}]
        policies.append(policy)

    permissions = [
        {
            "name": f"{INSTANCE_POLICY_PREFIX}permission:{resource}#{scope}",
            "type": "scope",
            "logic": "POSITIVE",
            "decisionStrategy": "AFFIRMATIVE",
            "resources": [resource],
            "scopes": [scope],
            "policies": sorted(policy_names),
        }
        for (resource, scope), policy_names in sorted(permission_subjects.items())
    ]
    return {
        "resources": [
            {
                "name": name,
                "type": "agentic:instance",
                "ownerManagedAccess": False,
                "scopes": scopes,
            }
            for name, scopes in sorted(resources.items())
        ],
        "policies": policies,
        "permissions": permissions,
    }


class ResourceAuthorizationProjectionRepository(BaseRepository):
    """Fail-closed, serialized projection of all direct resource grants."""

    def __init__(self, organization_repo=None, client=None, redis=None):
        super().__init__()
        self.organization_repo = organization_repo
        self.client = client or KeycloakRoleClient()
        self.redis = redis

    @asynccontextmanager
    async def _lock(self):
        settings = env
        if self.redis is not None:
            async with policy_write_lock(self.redis, settings.KEYCLOAK_REALM):
                yield self.redis
            return
        from redis.asyncio import Redis

        async with (
            Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
            ) as redis,
            policy_write_lock(redis, settings.KEYCLOAK_REALM),
        ):
            yield redis

    async def project_scoped_mutation(
        self,
        mutation: Callable[[], Awaitable[T]],
        *,
        target_type: str,
        target_id,
        resource_type: str,
        desired_resource_ids,
    ) -> T:
        """Project only the resources touched by an organization workspace save."""
        from src.service.keycloak_service import get_keycloak_service

        from .scoped_resource_projection import ScopedResourceProjection

        if target_type not in {"organization", "user"} or resource_type not in resource_clients():
            raise BadRequestError()
        async with get_keycloak_service().admin_request_scope(), self._lock() as redis:
            return await ScopedResourceProjection(self, redis).run(
                mutation, target_type, target_id, resource_type, desired_resource_ids
            )

    async def _target_resource_ids(self, target_type, target_id, resource_type):
        target = (
            ResourcePermissionModel.organization_id
            if target_type == "organization"
            else ResourcePermissionModel.user_id
        )
        async with self._session() as session:
            result = await session.execute(
                select(ResourcePermissionModel.resource_id).where(
                    target == target_id,
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.is_inherited.is_(False),
                )
            )
            return set(result.scalars())

    async def project_mutation(self, mutation: Callable[[], Awaitable[T]]) -> T:
        """Clear allows first, mutate SQL, then rebuild while holding the shared lock."""
        async with self._lock():
            await self.clear()
            result = await mutation()
            await self.reconcile_all()
            return result

    async def inventory(self, resource_type=None, resource_ids=None) -> list[dict[str, Any]]:
        if resource_ids is not None and not resource_ids:
            return []
        async with self._session() as session:
            query = select(ResourcePermissionModel).where(ResourcePermissionModel.is_inherited.is_(False))
            if resource_type is not None:
                query = query.where(ResourcePermissionModel.resource_type == resource_type)
            if resource_ids is not None:
                query = query.where(ResourcePermissionModel.resource_id.in_(resource_ids))
            result = await session.execute(query)
            rows = [
                {
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "organization_id": row.organization_id,
                    "user_id": row.user_id,
                    "permission_level": row.permission_level,
                }
                for row in result.scalars()
            ]
        organization_ids = {row["organization_id"] for row in rows if row["organization_id"] is not None}
        if organization_ids:
            if self.organization_repo is None:
                from .organization_repository import OrganizationRepository

                self.organization_repo = OrganizationRepository()
            active = {
                organization_id
                for organization_id in organization_ids
                if (organization := await self.organization_repo.get_by_id(organization_id))
                and organization.get("is_active", True)
            }
            rows = [row for row in rows if row["organization_id"] is None or row["organization_id"] in active]
        user_ids = {row["user_id"] for row in rows if row["user_id"] is not None}
        missing_users = set()
        for user_id in user_ids:
            user = await self.client.request("GET", "/users/" + quote(str(user_id), safe=""), missing=True)
            if user is None:
                missing_users.add(user_id)
        return [row for row in rows if row["user_id"] not in missing_users]

    async def clear(self) -> None:
        for client in await self.client.clients():
            if client["clientId"] not in resource_clients().values():
                continue
            base = f"/clients/{quote(client['id'], safe='')}/authz/resource-server"
            policies = await self.client.request("GET", base + "/policy", params={"max": -1})
            for policy in policies:
                if policy["name"].startswith(INSTANCE_POLICY_PREFIX):
                    # Deleting a policy can cascade to other entries in this snapshot.
                    await self.client.request(
                        "DELETE", base + "/policy/" + quote(policy["id"], safe=""), missing=True
                    )
            resources = await self.client.request("GET", base + "/resource", params={"max": -1})
            for resource in resources:
                if resource.get("type") == "agentic:instance":
                    await self.client.request(
                        "DELETE", base + "/resource/" + quote(resource["_id"], safe=""), missing=True
                    )

    async def reconcile_all(self) -> None:
        inventory = await self.inventory()
        clients = {client["clientId"]: client for client in await self.client.clients()}
        for resource_type, client_name in resource_clients().items():
            client = clients.get(client_name)
            if client is None:
                raise ConfigurationError()
            base = f"/clients/{quote(client['id'], safe='')}/authz/resource-server"
            objects = instance_authorization_objects(inventory, resource_type)
            for resource in objects["resources"]:
                await self.client.request("POST", base + "/resource", json=resource)
            for policy in objects["policies"]:
                await self.client.request("POST", base + f"/policy/{policy['type']}", json=policy)
            resources = await self.client.request("GET", base + "/resource", params={"max": -1})
            policies = await self.client.request("GET", base + "/policy", params={"max": -1})
            resource_ids = {
                resource["name"]: resource["_id"]
                for resource in resources
                if resource.get("type") == "agentic:instance"
            }
            policy_ids = {
                policy["name"]: policy["id"] for policy in policies if policy["name"].startswith(INSTANCE_POLICY_PREFIX)
            }
            for permission in objects["permissions"]:
                resolved = {
                    **permission,
                    "resources": [resource_ids[name] for name in permission["resources"]],
                    "policies": [policy_ids[name] for name in permission["policies"]],
                }
                await self.client.request("POST", base + "/permission/scope", json=resolved)

    async def reconcile_startup(self) -> None:
        """Bootstrap all existing SQL grants before the service accepts requests."""
        async with self._lock():
            await ensure_service_authorization(self.client)
            await self.clear()
            await self.reconcile_all()
