"""Bulk Keycloak read-back indexes for an offline, quiesced identity cutover.

Paginated group and role endpoints avoid large realm exports. Composite edges
are read independently so cross-client inherited realm roles remain complete.
"""

import asyncio
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import httpx

from src.core.observability import get_logger
from src.repository.keycloak_group_inventory import flatten_group_hierarchy, read_group_inventory

logger = get_logger(__name__)


class KeycloakCutoverInventory:
    """Serve verified identity GETs from a complete, explicitly refreshed snapshot.

    This adapter is for cutover verification while external writers are stopped,
    not a long-lived runtime cache. Unknown GETs warn once and use the real client.
    Successful writes invalidate profiles or the full assignment snapshot; the
    next indexed read reloads actual server data, never the submitted write body.
    """

    def __init__(self, keycloak, *, page_size=1000, concurrency=8):
        if page_size < 1 or concurrency < 1:
            raise ValueError("Inventory page size and concurrency must be positive")
        self.keycloak = keycloak
        self.page_size = page_size
        self.concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._refresh_lock = asyncio.Lock()
        self._dirty = {"all"}
        self._warned_paths = set()
        self.users = {}
        self.groups = {}
        self.memberships = {}
        self.effective_roles = {}
        self.realm_roles = {}

    @classmethod
    async def load(cls, keycloak, *, page_size=1000, concurrency=8):
        instance = cls(keycloak, page_size=page_size, concurrency=concurrency)
        await instance.refresh()
        return instance

    async def _network(self, method, path, **kwargs):
        async with self._semaphore:
            return await self.keycloak._keycloak_request(method, path, **kwargs)

    async def _json(self, method, path, **kwargs):
        response = await self._network(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def _pages(self, path, *, brief=False):
        async def fetch(first):
            params = {
                "first": first,
                "max": self.page_size,
                "briefRepresentation": "true" if brief else "false",
            }
            page = await self._json("GET", f"{path}?{urlencode(params)}")
            if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                raise ValueError(f"Invalid inventory page: {path}")
            return page

        result, seen = [], set()
        pages = [await fetch(0)]
        width = min(8, self.concurrency) if path.endswith("/users") else 1
        first = self.page_size
        while True:
            for page in pages:
                for row in page:
                    if not isinstance(row.get("id"), str) or not row["id"] or row["id"] in seen:
                        raise ValueError(f"Duplicate or missing identity in inventory page: {path}")
                    seen.add(row["id"])
                result.extend(page)
                if len(page) < self.page_size:
                    return result
            pages = await asyncio.gather(
                *(fetch(first + offset * self.page_size) for offset in range(width)),
                return_exceptions=True,
            )
            for page in pages:
                if isinstance(page, BaseException):
                    raise page
            first += width * self.page_size

    _flatten_groups = staticmethod(flatten_group_hierarchy)

    async def _role_catalog(self):
        realm = await self._pages("/roles")
        clients = await self._pages("/clients")
        rows = await asyncio.gather(
            *(self._pages(f"/clients/{quote(client['id'], safe='')}/roles") for client in clients)
        )
        client_roles = {client["clientId"]: roles for client, roles in zip(clients, rows, strict=True)}
        catalog = {"clients": clients, "roles": {"realm": realm, "client": client_roles}}
        by_id = {role["id"]: (None, role["name"]) for role in realm}
        for client, roles in client_roles.items():
            by_id.update({role["id"]: (client, role["name"]) for role in roles})

        async def composites(role):
            if not role.get("composite"):
                return
            children = await self._json("GET", f"/roles-by-id/{quote(role['id'], safe='')}/composites")
            if not isinstance(children, list):
                raise ValueError(f"Invalid composite role response: {role['name']}")
            graph = {"realm": [], "client": {}}
            for child in children:
                key = by_id.get(child.get("id"))
                if key is None:
                    raise ValueError(f"Unresolved composite role: {child.get('name')}")
                client, name = key
                if client is None:
                    graph["realm"].append(name)
                else:
                    graph["client"].setdefault(client, []).append(name)
            role["composites"] = graph

        await asyncio.gather(
            *(composites(role) for role in realm),
            *(composites(role) for roles in client_roles.values() for role in roles),
        )
        return catalog

    async def _group_role_mappings(self, groups):
        async def read(group):
            if "realmRoles" in group and "clientRoles" in group:
                return
            mappings = await self._json("GET", f"/groups/{quote(group['id'], safe='')}/role-mappings")
            group["realmRoles"] = [role["name"] for role in mappings.get("realmMappings") or []]
            group["clientRoles"] = {
                name: [role["name"] for role in mapped.get("mappings") or []]
                for name, mapped in (mappings.get("clientMappings") or {}).items()
            }

        await asyncio.gather(*(read(group) for group in groups.values()))

    @staticmethod
    def _role_graph(export):
        roles = {}
        catalog = export.get("roles") or {}
        for role in catalog.get("realm") or []:
            roles[(None, role["name"])] = role
        for client, client_roles in (catalog.get("client") or {}).items():
            for role in client_roles:
                roles[(client, role["name"])] = role
        edges = {}
        for key, role in roles.items():
            composite = role.get("composites") or {}
            children = {(None, name) for name in composite.get("realm") or []}
            children.update(
                (client, name) for client, names in (composite.get("client") or {}).items() for name in names
            )
            if role.get("composite") and not children:
                raise ValueError(f"Missing exported composite role edges: {key}")
            if not children.issubset(roles):
                raise ValueError(f"Unresolved composite role in Keycloak export: {key}")
            edges[key] = children
        closures = {}
        for key in roles:
            seen, pending = set(), [key]
            while pending:
                node = pending.pop()
                if node in seen:
                    continue
                seen.add(node)
                pending.extend(edges[node])
            closures[key] = {name for client, name in seen if client is None}
        return roles, closures

    async def _assignments(self, users, groups, export):
        # User listing omits service accounts, but role/group membership can include
        # them. Only the dedicated client endpoint proves that classification.
        accounts = await asyncio.gather(
            *(
                self._json("GET", f"/clients/{quote(client['id'], safe='')}/service-account-user")
                for client in export.get("clients") or []
                if client.get("serviceAccountsEnabled")
            )
        )
        if any(
            not isinstance(account, dict) or not isinstance(account.get("id"), str) or not account["id"]
            for account in accounts
        ):
            raise ValueError("Invalid Keycloak service account identity")
        service_accounts = {account["id"] for account in accounts}
        await self._group_role_mappings(groups)
        roles, closures = self._role_graph(export)
        realm_roles = {name: role for (client, name), role in roles.items() if client is None}
        clients = {client["clientId"]: client["id"] for client in export.get("clients") or []}
        memberships = {user_id: set() for user_id in users}
        effective = {user_id: set() for user_id in users}
        group_roles = {}
        for group_id, group in groups.items():
            inherited = set(group_roles.get(group["parentId"], set()))
            direct = {(None, name) for name in group.get("realmRoles") or []}
            direct.update(
                (client, name) for client, names in (group.get("clientRoles") or {}).items() for name in names
            )
            for role in direct:
                if role not in closures:
                    raise ValueError(f"Unresolved group role in Keycloak export: {role}")
                inherited.update(closures[role])
            group_roles[group_id] = inherited

        async def group_members(group_id):
            rows = await self._pages(f"/groups/{quote(group_id, safe='')}/members", brief=True)
            for member in rows:
                user_id = member["id"]
                if user_id not in users:
                    if user_id in service_accounts:
                        continue
                    raise ValueError(f"Group membership references absent user: {user_id}")
                memberships[user_id].add(group_id)
                effective[user_id].update(group_roles[group_id])

        async def role_members(key):
            client, name = key
            granted = closures[key]
            if not granted:
                return
            if client is None:
                path = f"/roles/{quote(name, safe='')}/users"
            else:
                if client not in clients:
                    raise ValueError(f"Missing Keycloak client in export: {client}")
                path = f"/clients/{quote(clients[client], safe='')}/roles/{quote(name, safe='')}/users"
            for member in await self._pages(path, brief=True):
                user_id = member["id"]
                if user_id not in users:
                    if user_id in service_accounts:
                        continue
                    raise ValueError(f"Role assignment references absent user: {user_id}")
                effective[user_id].update(granted)

        # Validate role assignees before the potentially much larger group pass.
        await asyncio.gather(*(role_members(key) for key in roles))
        await asyncio.gather(*(group_members(group_id) for group_id in groups))
        return memberships, effective, realm_roles

    async def refresh(self, *, full=True):
        """Re-read the server; full=False reloads only categories dirtied by writes."""
        async with self._refresh_lock:
            dirty = {"all"} if full else set(self._dirty)
            if not dirty:
                return self
            users = self.users
            groups = self.groups
            export = None
            if "all" in dirty or "users" in dirty:
                users = {user["id"]: user for user in await self._pages("/users")}
            if "all" in dirty or "groups" in dirty:
                groups = await read_group_inventory(
                    self.keycloak, page_size=self.page_size, concurrency=self.concurrency
                )
            if "all" in dirty:
                export = await self._role_catalog()
                memberships, effective, realm_roles = await self._assignments(users, groups, export)
                self.memberships, self.effective_roles, self.realm_roles = (
                    memberships,
                    effective,
                    realm_roles,
                )
            elif set(users) != set(self.users) or set(groups) != set(self.groups):
                # A supposedly metadata-only read detected concurrent identity changes.
                self._dirty.add("all")
                raise ValueError("Keycloak inventory changed during metadata reconciliation; refresh fully")
            self.users, self.groups = users, groups
            self._dirty.clear()
        return self

    @staticmethod
    def _response(method, path, data, *, status=200):
        return httpx.Response(status, json=data, request=httpx.Request(method, "https://keycloak-inventory" + path))

    async def _keycloak_request(self, method, path, **kwargs):
        parsed = urlsplit(path)
        parts = parsed.path.strip("/").split("/")
        indexed = method == "GET" and (
            (len(parts) == 2 and parts[0] in {"users", "groups"} and parts[1] not in {"profile", "count"})
            or (len(parts) == 3 and parts[0] == "users" and parts[2] == "groups")
            or (len(parts) == 5 and parts[0] == "users" and parts[2:] == ["role-mappings", "realm", "composite"])
        )
        if indexed:
            await self.refresh(full=False)
            identity = (self.users if parts[0] == "users" else self.groups).get(parts[1])
            if identity is None:
                return self._response(method, path, None, status=404)
            if len(parts) == 2:
                data = identity
            elif parts[2] == "groups":
                data = [self.groups[group_id] for group_id in sorted(self.memberships[parts[1]])]
                query = parse_qs(parsed.query)
                query.update({key: [str(value)] for key, value in kwargs.get("params", {}).items()})
                first = int(query.get("first", [0])[0])
                limit = int(query.get("max", [len(data)])[0])
                data = data[first : first + limit]
            else:
                data = [self.realm_roles[name] for name in sorted(self.effective_roles[parts[1]])]
            return self._response(method, path, data)
        if method == "GET" and parsed.path not in self._warned_paths:
            logger.warning("Keycloak inventory has no index for %s; falling through to live read", parsed.path)
            self._warned_paths.add(parsed.path)
        response = await self._network(method, path, **kwargs)
        if response.is_success and method not in {"GET", "HEAD"} and parsed.path != "/partial-export":
            payload = kwargs.get("json") or {}
            unchanged_group_name = (
                len(parts) == 2
                and parts[0] == "groups"
                and parts[1] in self.groups
                and payload.get("name") == self.groups[parts[1]]["name"]
            )
            if (
                method == "PUT"
                and len(parts) == 2
                and parts[0] in {"users", "groups"}
                and (
                    set(payload) <= {"attributes"} or (unchanged_group_name and set(payload) <= {"attributes", "name"})
                )
            ):
                self._dirty.add(parts[0])
            else:
                self._dirty.add("all")
        return response
