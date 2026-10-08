"""In-memory Keycloak admin role API for repository behaviour tests.

It models the realm-role, client-role and composite endpoints the role
repositories use. Keycloak assigns each role an immutable ``id`` when it is
created, so the fake does too and never reuses one.
"""

import copy
import uuid
from urllib.parse import unquote

from src.repository.keycloak_role_client import KeycloakRoleClient, catalog_cache


class FakeKeycloakRoles(KeycloakRoleClient):
    def __init__(self):
        self.clients_by_id: dict[str, dict] = {}
        self.roles: dict[str, dict] = {}
        self.composites: dict[str, list[str]] = {}
        self.calls: list[tuple[str, str]] = []

    # -- seeding --------------------------------------------------------

    def add_client(self, client_id: str) -> str:
        internal = str(uuid.uuid4())
        self.clients_by_id[internal] = {"id": internal, "clientId": client_id}
        return internal

    def add_realm_role(self, name: str, attributes: dict | None = None, **extra) -> str:
        return self._store(name, None, attributes, extra)

    def add_client_role(self, client_uuid: str, name: str, attributes: dict | None = None) -> str:
        return self._store(name, client_uuid, attributes, {})

    def link(self, parent_id: str, *child_ids: str) -> None:
        self.composites.setdefault(parent_id, []).extend(child_ids)

    def _store(self, name, container, attributes, extra) -> str:
        role_id = str(uuid.uuid4())
        self.roles[role_id] = {
            "id": role_id,
            "name": name,
            "description": extra.get("description", ""),
            "clientRole": container is not None,
            "containerId": container or "realm",
            "attributes": copy.deepcopy(attributes or {}),
        }
        return role_id

    # -- transport ------------------------------------------------------

    def _view(self, role_id: str) -> dict:
        role = copy.deepcopy(self.roles[role_id])
        role["composite"] = bool(self.composites.get(role_id))
        return role

    def _realm(self, name):
        return next(
            (i for i, r in self.roles.items() if not r["clientRole"] and r["name"] == name), None
        )

    def _client_role(self, container, name):
        return next(
            (
                i
                for i, r in self.roles.items()
                if r["containerId"] == container and r["name"] == name
            ),
            None,
        )

    async def request(self, method, path, *, missing=False, **kwargs):
        self.calls.append((method, path))
        if method != "GET":
            catalog_cache.clear()
        parts = [unquote(part) for part in path.strip("/").split("/")]
        params = kwargs.get("params") or {}
        body = kwargs.get("json")
        result = self._dispatch(method, parts, params, body)
        if result is _MISSING:
            if missing:
                return None
            raise LookupError(f"404 {method} {path}")
        return result

    def _dispatch(self, method, parts, params, body):
        head, rest = parts[0], parts[1:]
        if head == "roles":
            return self._realm_roles(method, rest, params, body)
        if head == "roles-by-id":
            return self._role_by_id(method, rest, body)
        if head == "clients" and not rest:
            return self._clients(params)
        if head == "clients" and rest[1] == "roles":
            return self._client_roles(method, rest[0], rest[2:], params, body)
        raise NotImplementedError(f"{method} /{'/'.join(parts)}")

    def _create(self, name, container, body):
        existing = self._client_role(container, name) if container else self._realm(name)
        if existing:
            raise ValueError("409 role exists")
        role_id = self._store(name, container, body.get("attributes"), {})
        self.roles[role_id]["description"] = body.get("description", "")

    def _realm_roles(self, method, rest, params, body):
        if rest:
            role_id = self._realm(rest[0])
            return self._view(role_id) if role_id else _MISSING
        if method == "POST":
            return self._create(body["name"], None, body)
        realm = [self._view(i) for i, r in self.roles.items() if not r["clientRole"]]
        return self._page(realm, params)

    def _role_by_id(self, method, rest, body):
        role_id = rest[0]
        if role_id not in self.roles:
            return _MISSING
        if len(rest) > 1:
            return self._composites(method, role_id, body)
        if method == "PUT":
            stored = self.roles[role_id]
            stored["description"] = body.get("description", "")
            stored["attributes"] = copy.deepcopy(body.get("attributes", {}))
            return None
        if method == "DELETE":
            del self.roles[role_id]
            self.composites.pop(role_id, None)
            return None
        return self._view(role_id)

    def _composites(self, method, role_id, body):
        children = self.composites.setdefault(role_id, [])
        if method == "POST":
            children.extend(r["id"] for r in body if r["id"] not in children)
            return None
        if method == "DELETE":
            removed = {r["id"] for r in body}
            self.composites[role_id] = [c for c in children if c not in removed]
            return None
        return [self._view(child) for child in children if child in self.roles]

    def _clients(self, params):
        rows = list(self.clients_by_id.values())
        if "clientId" in params:
            return [c for c in rows if c["clientId"] == params["clientId"]]
        return self._page(rows, params)

    def _client_roles(self, method, container, rest, params, body):
        if rest:
            role_id = self._client_role(container, rest[0])
            return self._view(role_id) if role_id else _MISSING
        if method == "POST":
            return self._create(body["name"], container, body)
        rows = [self._view(i) for i, r in self.roles.items() if r["containerId"] == container]
        return self._page(rows, params)

    @staticmethod
    def _page(rows, params):
        first = int(params.get("first", 0))
        size = int(params.get("max", len(rows) or 1))
        return rows[first : first + size]


_MISSING = object()
