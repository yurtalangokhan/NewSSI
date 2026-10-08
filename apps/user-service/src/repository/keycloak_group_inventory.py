"""Read complete group hierarchies without a request for every child group."""

from collections import defaultdict, deque
from contextlib import nullcontext
from urllib.parse import urlencode

from error_contract import DependencyResponseError, raise_for_httpx_response


def flatten_group_hierarchy(roots):
    """Index full exported groups in parent-before-child order."""
    groups = {}
    pending = [(group, None, "") for group in reversed(roots)]
    while pending:
        group, parent_id, parent_path = pending.pop()
        group_id = group.get("id")
        if not group_id or group_id in groups:
            raise DependencyResponseError()
        children = group.get("subGroups") or []
        child_count = group.get("subGroupCount")
        if child_count is not None and child_count != len(children):
            raise DependencyResponseError()
        data = {key: value for key, value in group.items() if key != "subGroups"}
        data["parentId"] = parent_id
        data["path"] = group.get("path") or f"{parent_path}/{group['name']}"
        groups[group_id] = data
        pending.extend((child, group_id, data["path"]) for child in reversed(children))
    return groups


async def read_group_inventory(keycloak, *, page_size=1000, concurrency=8):
    """Read all groups with an explicit empty search, then validate the hierarchy.

    Keycloak distinguishes an empty search from an omitted search (roots only).
    A realm-wide count prevents accepting a truncated or roots-only response.
    """
    if page_size < 1 or concurrency < 1:
        raise DependencyResponseError()
    scope = getattr(type(keycloak), "admin_request_scope", None)
    async with scope(keycloak) if scope else nullcontext():
        return await _read_group_pages(keycloak, page_size=page_size)


async def _read_group_pages(keycloak, *, page_size):
    response = await keycloak._keycloak_request("GET", "/groups/count?top=false")
    raise_for_httpx_response(response)
    expected = response.json().get("count")
    if type(expected) is not int or expected < 0:
        raise DependencyResponseError()
    groups = {}
    while len(groups) < expected:
        query = urlencode(
            {
                "search": "",
                "first": len(groups),
                "max": page_size,
                "populateHierarchy": "false",
                "briefRepresentation": "false",
            }
        )
        response = await keycloak._keycloak_request("GET", f"/groups?{query}")
        raise_for_httpx_response(response)
        page = response.json()
        if not isinstance(page, list):
            raise DependencyResponseError()
        for group in page:
            group_id = group.get("id")
            if not group_id or group_id in groups:
                raise DependencyResponseError()
            groups[group_id] = {key: value for key, value in group.items() if key != "subGroups"}
        if len(page) < page_size:
            break
    if len(groups) != expected:
        raise DependencyResponseError()
    return _order_flat_groups(groups)


def _order_flat_groups(groups):
    paths = {}
    for group_id, group in groups.items():
        path = group.get("path")
        if path:
            if path in paths:
                raise DependencyResponseError()
            paths[path] = group_id
    children = defaultdict(list)
    for group_id, group in groups.items():
        parent_id = group.get("parentId")
        if "parentId" not in group and group.get("path"):
            parent_path = group["path"].rsplit("/", 1)[0]
            if parent_path:
                parent_id = paths.get(parent_path)
                if parent_id is None:
                    raise DependencyResponseError()
        if parent_id is not None and parent_id not in groups:
            raise DependencyResponseError()
        group["parentId"] = parent_id
        children[parent_id].append(group_id)
    ordered = {}
    pending = deque(children[None])
    while pending:
        group_id = pending.popleft()
        group = groups[group_id]
        count = len(children[group_id])
        if group.get("subGroupCount") is not None and group["subGroupCount"] != count:
            raise DependencyResponseError()
        parent = ordered.get(group["parentId"])
        group.setdefault("path", f"{parent['path'] if parent else ''}/{group['name']}")
        ordered[group_id] = group
        pending.extend(children[group_id])
    if len(ordered) != len(groups):
        raise DependencyResponseError()
    return ordered
