#!/usr/bin/env python3
"""Generate the fail-closed gateway inventory and Keycloak authorization settings.

Uses source AST, never imports applications or requires running databases.
"""

import argparse
import ast
import importlib.util
import json
import re
from pathlib import Path


def name(node):
    return node.id if isinstance(node, ast.Name) else ""


def path_regex(path):
    parts = re.split(r"(\{[^}]+\})", path.rstrip("/"))
    return (
        "^"
        + "".join(
            (".+" if ":path}" in part else "[^/]+")
            if part.startswith("{")
            else re.escape(part).replace(r"\-", "-")
            for part in parts
        )
        + "/?$"
    )


def route_rows(source, audience, resource_prefix=""):
    tree = ast.parse(source)
    routers = {}
    aliases = {
        name(node.targets[0]): node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and name(node.value.func)
        in {"require_permission", "require_permission_or_admin"}
    }
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and name(node.value.func) == "APIRouter"
        ):
            prefix = next(
                (
                    ast.literal_eval(k.value)
                    for k in node.value.keywords
                    if k.arg == "prefix"
                ),
                "",
            )
            routers[name(node.targets[0])] = (prefix, node.value)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(
                decorator.func, ast.Attribute
            ):
                continue
            router = routers.get(name(decorator.func.value))
            if not router or decorator.func.attr not in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "head",
                "options",
            }:
                continue
            path = router[0] + ast.literal_eval(decorator.args[0])
            internal = path.startswith("/internal")
            nodes = [router[1], node.args, *node.decorator_list]
            referenced = {
                call.id
                for root in nodes
                for call in ast.walk(root)
                if isinstance(call, ast.Name)
            }
            nodes.extend(value for key, value in aliases.items() if key in referenced)
            permissions = sorted(
                {
                    ast.literal_eval(call.args[0]).replace(":", "#", 1)
                    for root in nodes
                    for call in ast.walk(root)
                    if isinstance(call, ast.Call)
                    and name(call.func)
                    in {"require_permission", "require_permission_or_admin"}
                }
            )
            authenticated = any(
                isinstance(call, ast.Name)
                and call.id
                in {
                    "require_auth",
                    "require_user",
                    "require_auth_or_internal_service_token",
                    "require_user_or_internal_service_token",
                    "get_current_user",
                    "_internal_identity",
                    "require_internal_service_token",
                }
                for root in nodes
                for call in ast.walk(root)
            )
            # A route that accepts only the internal service token is never
            # published on the user-facing path, not even to be refused there.
            internal_only = any(
                isinstance(call, ast.Name) and call.id == "require_internal_service_token"
                for root in nodes
                for call in ast.walk(root)
            )
            if not permissions and not authenticated:
                public_paths = {
                    "user-service": {
                        "",
                        "/",
                        "/ready",
                        "/auth/type",
                        "/auth/login",
                        "/auth/external/login",
                        "/auth/logout",
                        "/auth/refresh",
                        "/auth/oidc/authorize",
                        "/auth/oidc/callback",
                        "/auth/register",
                    },
                    "agent-service": {"/health"},
                    "rag-service": {"/graph/health"},
                }
                if path not in public_paths.get(audience, set()):
                    raise ValueError(
                        f"Unclassified gateway endpoint: {audience} {path}"
                    )
                continue
            if audience == "agent-service":
                path = path[4:] if path.startswith("/api/") else resource_prefix + path
            full_path = f"/{audience}/api/v1{path}"
            if internal:
                full_path = "/internal" + full_path
            row = {
                "path": path_regex(full_path),
                "methods": [decorator.func.attr.upper()],
                "audience": audience,
                "permissions": permissions,
            }
            if not permissions:
                row["authenticated_only"] = True
            if internal_only:
                row["internal_only"] = True
            yield row


# Router files each service's gateway inventory is read from. The Keycloak
# bootstrap container must mount these paths (deploy/docker compose).
# rag-service keeps one router per domain package (src/<domain>/router.py).
ROUTE_GLOBS = {
    "user-service": "src/api/routes/*.py",
    "agent-service": "src/api/routes/*.py",
    "rag-service": "src/*/router.py",
}


def inventory(root):
    rows = []
    for service, pattern in ROUTE_GLOBS.items():
        for path in sorted((root / "apps" / service).glob(pattern)):
            prefix = {
                "AuthRoute.py": "/auth",
                "auth_route.py": "/auth",
                "IngestRoute.py": "/ingest",
                "ingest_route.py": "/ingest",
            }.get(
                path.name, ""
            )
            rows.extend(
                route_rows(path.read_text(encoding="utf-8-sig"), service, prefix)
            )
    # MCP methods are authorized per tool by the trusted invocation middleware.
    rows.append(
        {
            "path": "^/tools-service/mcp/?$",
            "methods": ["GET", "POST", "DELETE"],
            "audience": "tools-service",
            "permissions": [],
            "authenticated_only": True,
        }
    )
    rows.extend(
        {**row, "path": "^/internal" + row["path"][1:]}
        for row in list(rows)
        if row["audience"] in {"user-service", "rag-service", "tools-service"}
        and not row["path"].startswith("^/internal/")
    )
    # The memory index is called by user-service and agent-service only.
    # Keep its internal gateway paths, but deny direct browser access.
    rows = [
        row
        for row in rows
        if not (
            row["audience"] == "rag-service"
            and row["path"].startswith("^/rag-service/api/v1/memory/")
        )
    ]
    # Routes marked internal_only (stored connector configurations) are served
    # to services only: keep their internal paths, drop the browser ones.
    rows = [
        {key: value for key, value in row.items() if key != "internal_only"}
        for row in rows
        if not row.get("internal_only") or row["path"].startswith("^/internal/")
    ]
    # Literal routes must precede parameter routes, matching FastAPI routing semantics.
    rows.sort(
        key=lambda row: (
            row["path"].count("[^/]+"),
            -len(row["path"]),
            row["path"],
            row["methods"],
        )
    )
    return [{**row, "audience": f"{row['audience']}-client"} for row in rows]


# Load the shared policy projection without importing the application package.
_shared_path = (
    Path(__file__).resolve().parents[1]
    / "apps/user-service/src/repository/keycloak_authorization.py"
)
_shared_spec = importlib.util.spec_from_file_location(
    "keycloak_authorization", _shared_path
)
_shared = importlib.util.module_from_spec(_shared_spec)
_shared_spec.loader.exec_module(_shared)
authorization_settings = _shared.authorization_settings
reconcile = _shared.reconcile

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(inventory(Path(__file__).resolve().parents[1]), indent=2) + "\n",
        encoding="utf-8",
    )
