"""Organization contracts backed exclusively by Keycloak groups."""

import asyncio
from collections import Counter
from contextlib import nullcontext
from datetime import UTC, datetime
import json
from typing import Any
from urllib.parse import urlencode
import uuid

from error_contract import BadRequestError, DependencyResponseError, NotFoundError
from error_contract.identity import ConflictError

from .keycloak_group_client import KeycloakGroupClient
from .keycloak_group_inventory import read_group_inventory

PREFIX = "agenticai.organization."


class OrganizationRepository:
    def __init__(self, keycloak=None):
        self.client = KeycloakGroupClient(keycloak)

    async def _all(self):
        groups = await read_group_inventory(self.client.keycloak)
        children = Counter(group["parentId"] for group in groups.values())
        organizations = {}
        for group_id, group in groups.items():
            parent = organizations.get(group["parentId"])
            data = self._to_dict(
                group,
                parent["id"] if parent else None,
                f"{parent['path']}{parent['id']}/" if parent else "/",
                parent["level"] + 1 if parent else 0,
            )
            count = children[group_id]
            data.update(children_count=count, has_children=count > 0)
            organizations[group_id] = data
        return sorted(organizations.values(), key=lambda item: (item["level"], item["order_index"]))

    @staticmethod
    def _to_dict(group, parent_id=None, path="/", level=0):
        attrs = group.get("attributes") or {}

        def value(field, default=None):
            stored = attrs.get(PREFIX + field)
            return json.loads(stored[0]) if stored else default

        return {
            "id": uuid.UUID(group["id"]),
            "name": group["name"],
            "code": value("code", group["id"]),
            "description": value("description"),
            "parent_id": parent_id,
            "path": path,
            "level": level,
            "order_index": value("order_index", 0),
            "is_active": value("is_active", True),
            "metadata": value("metadata", {}),
            "created_at": value("created_at"),
            "updated_at": value("updated_at"),
            "created_by": uuid.UUID(value("created_by")) if value("created_by") else None,
        }

    async def get_by_id(self, org_id):
        groups = await self._get_by_ids([org_id])
        return groups[0] if groups else None

    def _request_scope(self):
        scope = getattr(type(self.client.keycloak), "admin_request_scope", None)
        return scope(self.client.keycloak) if scope else nullcontext()

    async def _get_by_ids(self, org_ids, *, _cache=None):
        """Resolve selected groups with an operation-local cache of their ancestors."""
        async with self._request_scope():
            cache = {} if _cache is None else _cache
            result = []
            for org_id in dict.fromkeys(str(value) for value in org_ids):
                chain, seen = [], set()
                current = org_id
                while current:
                    if current in seen:
                        raise DependencyResponseError()
                    seen.add(current)
                    if current not in cache:
                        cache[current] = await self.client.get(f"/groups/{current}")
                    group = cache[current]
                    if group is None:
                        if chain:
                            raise DependencyResponseError()
                        break
                    chain.append(group)
                    current = group.get("parentId")
                if not chain:
                    continue
                group = chain[0]
                ancestors = list(reversed(chain[1:]))
                data = self._to_dict(
                    group,
                    uuid.UUID(chain[1]["id"]) if ancestors else None,
                    "/" + "".join(f"{ancestor['id']}/" for ancestor in ancestors),
                    len(ancestors),
                )
                count = group.get("subGroupCount")
                if count is None:
                    count = len(await self.client.pages(f"/groups/{org_id}/children"))
                data.update(children_count=count, has_children=count > 0)
                result.append(data)
            return sorted(result, key=lambda item: (item["level"], item["order_index"]))

    async def get_by_code(self, code):
        return next((g for g in await self._all() if g["code"] == code), None)

    async def create(self, name, code, parent_id=None, description=None, created_by=None, metadata=None):
        groups = await self._all()
        if any(g["code"] == code for g in groups):
            raise ConflictError(
                message_key="errors.user_service.organization.organization_with_code_already_exists",
                message_params={"param1": code},
            )
        if parent_id is None and groups:
            raise ConflictError(message_key="errors.user_service.organization.a_root_organization_already_exists")
        if parent_id is not None and not any(g["id"] == parent_id for g in groups):
            raise NotFoundError()
        now = datetime.now(UTC).isoformat()
        fields = {
            "code": code,
            "description": description,
            "created_by": str(created_by) if created_by else None,
            "metadata": metadata or {},
            "is_active": True,
            "order_index": 0,
            "created_at": now,
            "updated_at": now,
        }
        payload = {
            "name": name,
            "attributes": {PREFIX + k: [json.dumps(v)] for k, v in fields.items()},
        }
        path = f"/groups/{parent_id}/children" if parent_id else "/groups"
        response = await self.client.request("POST", path, json=payload)
        if response is None:
            raise NotFoundError()
        location = response.headers.get("Location", "")
        if location:
            return await self.get_by_id(location.rstrip("/").rsplit("/", 1)[-1])
        return await self.get_by_code(code)

    async def update(self, org_id, **updates):
        if "is_active" in updates:
            from .keycloak_resource_authorization import project_resource_permission_mutation

            return await project_resource_permission_mutation(lambda: self._update(org_id, **updates))
        return await self._update(org_id, **updates)

    async def _update(self, org_id, **updates):
        group = await self.client.get(f"/groups/{org_id}")
        if group is None:
            return None
        attrs = dict(group.get("attributes") or {})
        for key in ("code", "description", "order_index", "is_active", "metadata", "created_by"):
            val = updates.get(key, updates.get("metadata_json") if key == "metadata" else None)
            if val is not None:
                attrs[PREFIX + key] = [json.dumps(val, default=str)]
        attrs[PREFIX + "updated_at"] = [json.dumps(datetime.now(UTC).isoformat())]
        payload = {"name": updates.get("name") or group["name"], "attributes": attrs}
        await self.client.request("PUT", f"/groups/{org_id}", json=payload)
        return await self.get_by_id(org_id)

    async def delete(self, org_id):
        from .keycloak_resource_authorization import project_resource_permission_mutation
        from .resource_permission_repository import ResourcePermissionRepository

        groups = await self.get_scoped_organizations([org_id])
        if not groups:
            return False

        async def delete_subtree():
            response = await self.client.request("DELETE", f"/groups/{org_id}")
            if response is None:
                return False
            permissions = ResourcePermissionRepository()
            for group in groups:
                await permissions.delete_organization_permissions(group["id"])
            return True

        return await project_resource_permission_mutation(delete_subtree)

    async def list_all(self, skip=0, limit=100, is_active=None, parent_id=None):
        groups = [
            g
            for g in await self._all()
            if (is_active is None or g["is_active"] == is_active) and (parent_id is None or g["parent_id"] == parent_id)
        ]
        return groups[skip : skip + limit], len(groups)

    async def get_scoped_organizations(self, root_ids):
        ids = {str(i) for i in root_ids}
        if not ids:
            return []
        return [g for g in await self._all() if str(g["id"]) in ids or ids.intersection(g["path"].split("/"))]

    async def get_manager_roots(self, actor_id):
        from .user_organization_repository import UserOrganizationRepository

        memberships = await UserOrganizationRepository(self.client.keycloak).get_active_unit_manager_organizations(
            actor_id
        )
        ids = {m["organization_id"] for m in memberships}
        return await self._get_by_ids(ids)

    async def count_scoped_permissions(self, organization_ids):
        from .resource_permission_repository import ResourcePermissionRepository

        repo = ResourcePermissionRepository()
        total = 0
        for org_id in organization_ids:
            total += len(await repo.get_organization_permissions(org_id))
        return total

    async def get_children(self, parent_id, direct_only=True):
        groups = await self._branch_groups(parent_id, 1 if direct_only else None)
        return [group for group in groups if str(group["id"]) != str(parent_id)]

    async def get_ancestors(self, org_id):
        async with self._request_scope():
            cache = {}
            target = await self._get_by_ids([org_id], _cache=cache)
            if not target:
                return []
            ancestors = [value for value in target[0]["path"].split("/") if value]
            return await self._get_by_ids(ancestors, _cache=cache)

    async def _branch_groups(self, root_id, max_depth):
        """Read only the requested depth, retaining counts for unexpanded nodes."""
        async with self._request_scope():
            page_cache = {}
            semaphore = asyncio.Semaphore(8)

            async def children(parent_id):
                if parent_id in page_cache:
                    return page_cache[parent_id]
                path = f"/groups/{parent_id}/children" if parent_id else "/groups"
                rows, seen = [], set()
                while True:
                    query = urlencode(
                        {
                            "first": len(rows),
                            "max": 1000,
                            "briefRepresentation": "false",
                            "populateHierarchy": "false",
                        }
                    )
                    async with semaphore:
                        page = await self.client.get(f"{path}?{query}")
                    if page is None:
                        page = []
                    if not isinstance(page, list):
                        raise DependencyResponseError()
                    for group in page:
                        if not group.get("id") or group["id"] in seen:
                            raise DependencyResponseError()
                        seen.add(group["id"])
                    rows.extend(page)
                    if len(page) < 1000:
                        page_cache[parent_id] = rows
                        return rows

            async def convert(group, parent=None):
                expected_parent = str(parent["id"]) if parent else None
                if group.get("parentId") not in (None, expected_parent):
                    raise DependencyResponseError()
                data = self._to_dict(
                    group,
                    parent["id"] if parent else None,
                    f"{parent['path']}{parent['id']}/" if parent else "/",
                    parent["level"] + 1 if parent else 0,
                )
                count = group.get("subGroupCount")
                if count is None:
                    count = len(await children(group["id"]))
                data.update(children_count=count, has_children=count > 0)
                return data

            if root_id is not None:
                root = await self.get_by_id(root_id)
                frontier = [root] if root else []
            else:
                frontier = list(await asyncio.gather(*(convert(group) for group in await children(None))))
            groups = list(frontier)
            seen = {group["id"] for group in groups}
            depth = 0
            while frontier and (max_depth is None or depth < max_depth):
                parents = [parent for parent in frontier if parent["has_children"]]
                pages = await asyncio.gather(*(children(str(parent["id"])) for parent in parents))
                frontier = []
                for parent, page in zip(parents, pages, strict=True):
                    if len(page) != parent["children_count"]:
                        raise DependencyResponseError()
                    for group in page:
                        child = await convert(group, parent)
                        if child["id"] in seen:
                            raise DependencyResponseError()
                        seen.add(child["id"])
                        frontier.append(child)
                groups.extend(frontier)
                depth += 1
            return sorted(groups, key=lambda item: (item["level"], item["order_index"]))

    async def move_organization(self, org_id, new_parent_id):
        org = await self.get_by_id(org_id)
        if not org:
            return None
        if new_parent_id is not None:
            parent = await self.get_by_id(new_parent_id)
            if not parent:
                raise NotFoundError()
            if org_id == new_parent_id or str(org_id) in parent["path"].split("/"):
                raise BadRequestError()
        elif org["parent_id"] is not None:
            raise ConflictError(message_key="errors.user_service.organization.a_root_organization_already_exists")
        path = f"/groups/{new_parent_id}/children" if new_parent_id else "/groups"
        await self.client.request("POST", path, json={"id": str(org_id), "name": org["name"]})
        return await self.get_by_id(org_id)

    async def search(self, query, max_results=20):
        terms = query.lower().split()
        if not terms:
            return []
        return sorted(
            [
                g
                for g in await self._all()
                if all(
                    any(term in str(g.get(field) or "").lower() for field in ("name", "code", "description"))
                    for term in terms
                )
            ],
            key=lambda g: g["name"],
        )[:max_results]

    async def get_tree(self, root_id=None, max_depth=None) -> dict[str, Any]:
        groups = (
            await self._all()
            if root_id is None and max_depth is None
            else await self._branch_groups(root_id, max_depth)
        )
        root = next((g for g in groups if g["id"] == root_id), None)
        if root_id and root is None:
            raise NotFoundError()
        depth = root["level"] if root else 0
        selected = {
            g["id"]: {**g, "children": []}
            for g in groups
            if (root_id is None or g["id"] == root_id or str(root_id) in g["path"].split("/"))
            and (max_depth is None or g["level"] <= depth + max_depth)
        }
        roots = []
        for group in selected.values():
            parent = selected.get(group["parent_id"])
            if parent:
                parent["children"].append(group)
            else:
                roots.append(group)
        return selected[root_id] if root_id else {"roots": roots}

    async def get_stats(self):
        from .user_organization_repository import UserOrganizationRepository

        groups = await self._all()
        members = await UserOrganizationRepository(self.client.keycloak).get_all_active_organization_users()
        return {
            "total_organizations": len(groups),
            "total_users": len({m["user_id"] for m in members}),
            "total_permissions": await self.count_scoped_permissions([g["id"] for g in groups]),
            "organizations_by_depth": dict(Counter(g["level"] for g in groups)),
        }
