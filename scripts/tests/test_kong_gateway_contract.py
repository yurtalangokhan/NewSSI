import ast
import re
import unittest
from pathlib import Path
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KONG_CONFIG_FILE = REPOSITORY_ROOT / "configs" / "kong" / "kong.yml"
WEB_SOURCE_ROOT = REPOSITORY_ROOT / "apps" / "web" / "src"
USER_SERVICE_ROUTES_ROOT = REPOSITORY_ROOT / "apps" / "user-service" / "src" / "api" / "routes"
PYTHON_SERVICE_ROOTS = (
    REPOSITORY_ROOT / "apps" / "user-service" / "src",
    REPOSITORY_ROOT / "apps" / "agent-service" / "src",
    REPOSITORY_ROOT / "apps" / "rag-service" / "langconnect",
)
INTERNAL_GATEWAY_ROUTE_MATRIX = {
    "/internal/user-service": (
        "internal-user-service",
        "__USER_SERVICE_UPSTREAM_URL__",
        REPOSITORY_ROOT / "apps" / "user-service" / "src",
        ("require_auth_or_internal_service_token",),
    ),
    "/internal/rag-service": (
        "internal-rag-service",
        "__RAG_SERVICE_UPSTREAM_URL__",
        REPOSITORY_ROOT / "apps" / "rag-service" / "langconnect",
        ("X-Internal-Service-Token", "internal-service", "INTERNAL_SERVICE_TOKEN"),
    ),
    "/internal/tools-service": (
        "internal-tools-service",
        "__TOOLS_SERVICE_UPSTREAM_URL__",
        REPOSITORY_ROOT / "apps" / "tools-service",
        ("X-Internal-Service-Token", "INTERNAL_SERVICE_TOKEN"),
    ),
}

PUBLIC_AUTH_COMPATIBILITY_MATRIX = {
    "/api/auth/type": "legacy-public",
    "/api/auth/login": "legacy-public",
    "/api/auth/ldap/login": "legacy-public-or-out-of-scope",
    "/api/auth/external/login": "legacy-public",
    "/api/auth/logout": "legacy-public",
    "/api/auth/refresh": "legacy-public",
    "/api/auth/oidc/authorize": "legacy-public",
    "/api/auth/oidc/callback": "legacy-public",
    "/api/auth/oauth/authorize": "legacy-public-or-out-of-scope",
    "/api/auth/oauth/callback": "legacy-public-or-out-of-scope",
    "/api/auth/saml/callback": "legacy-public-or-out-of-scope",
    "/api/auth/saml/logout": "legacy-public-or-out-of-scope",
    "/api/auth/register": "legacy-public",
    "/api/auth/request-verify-token": "legacy-public-or-out-of-scope",
    "/api/auth/verify": "legacy-public-or-out-of-scope",
    "/api/auth/forgot-password": "legacy-public-or-out-of-scope",
    "/api/auth/reset-password": "legacy-public-or-out-of-scope",
    "/api/auth/me": "legacy-protected",
}

CANONICAL_USER_INTERNAL_ROUTES = {
    "/internal/users/upsert-from-keycloak",
    "/internal/users/by-keycloak-id/{keycloak_id}",
    "/internal/users/{target_id}",
    "/internal/users/{target_id}/permissions",
    "/internal/users/authorize",
    "/internal/users/{target_id}/settings",
    "/internal/users/{target_id}/settings/prompt-shortcuts",
    "/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}",
    "/internal/users/{target_id}/memories",
    "/internal/users/{target_id}/memories/recall",
    "/internal/users/{target_id}/memories/bulk",
    "/internal/users/{target_id}/memories/{memory_id}",
}


def _load_kong_config() -> dict[str, Any]:
    return yaml.safe_load(KONG_CONFIG_FILE.read_text(encoding="utf-8"))


def _routes_by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    for service in config["services"]:
        for route in service.get("routes", []):
            if route["name"] in routes:
                raise AssertionError(f"Duplicate Kong route name: {route['name']}")
            route_with_service = dict(route)
            route_with_service["_service_name"] = service["name"]
            route_with_service["_service_url"] = service["url"]
            routes[route["name"]] = route_with_service
    return routes


def _routes_with_path(config: dict[str, Any], path: str) -> list[dict[str, Any]]:
    return [
        route
        for route in _routes_by_name(config).values()
        if path in route.get("paths", [])
    ]


def _has_jwt_plugin(route: dict[str, Any]) -> bool:
    return any(plugin.get("name") == "jwt" for plugin in route.get("plugins", []))


def _source_contains_any(root: Path, signals: tuple[str, ...]) -> bool:
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(signal in text for signal in signals):
            return True
    return False


def _string_literals(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _web_auth_paths() -> set[str]:
    paths: set[str] = set()
    for path in WEB_SOURCE_ROOT.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        for literal in _string_literals(path):
            paths.update(re.findall(r"/api/auth/[A-Za-z0-9_./{}-]+", literal))
    return {path.rstrip("/") for path in paths}


def _python_route_paths(source_root: Path) -> set[str]:
    paths: set[str] = set()
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        router_prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if not isinstance(func, ast.Name) or func.id != "APIRouter":
                continue
            prefix = ""
            for keyword in node.value.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                    prefix = str(keyword.value.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    router_prefixes[target.id] = prefix

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    continue
                router_name = (
                    decorator.func.value.id
                    if isinstance(decorator.func.value, ast.Name)
                    else ""
                )
                paths.add(f"{router_prefixes.get(router_name, '')}{decorator.args[0].value}")
    return paths


def _user_service_internal_routes_without_internal_dependency() -> list[str]:
    missing_dependency: list[str] = []
    expected_routes = CANONICAL_USER_INTERNAL_ROUTES | {
        route.replace("/internal/users", "/users/internal", 1)
        for route in CANONICAL_USER_INTERNAL_ROUTES
        if route.startswith("/internal/users")
    }

    for path in USER_SERVICE_ROUTES_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        router_prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if not isinstance(func, ast.Name) or func.id != "APIRouter":
                continue
            prefix = ""
            for keyword in node.value.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                    prefix = str(keyword.value.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    router_prefixes[target.id] = prefix

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_paths: list[str] = []
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    continue
                router_name = (
                    decorator.func.value.id
                    if isinstance(decorator.func.value, ast.Name)
                    else ""
                )
                route_paths.append(
                    f"{router_prefixes.get(router_name, '')}{decorator.args[0].value}"
                )

            if not route_paths:
                continue
            source = ast.get_source_segment(text, node) or ""
            for route_path in route_paths:
                if route_path in expected_routes and "require_auth_or_internal_service_token" not in source:
                    missing_dependency.append(route_path)

    return sorted(missing_dependency)


class KongGatewayContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _load_kong_config()

    def test_service_scoped_health_routes_are_public(self) -> None:
        expected_routes = {
            "/user-service/health": (
                "__USER_SERVICE_UPSTREAM_URL__",
                "/api/v1/health",
            ),
            "/user-service/api/v1/health": (
                "__USER_SERVICE_UPSTREAM_URL__",
                "/api/v1/health",
            ),
            "/user-service/health/ready": (
                "__USER_SERVICE_UPSTREAM_URL__",
                "/api/v1/health/ready",
            ),
            "/user-service/api/v1/health/ready": (
                "__USER_SERVICE_UPSTREAM_URL__",
                "/api/v1/health/ready",
            ),
            "/agent-service/health": (
                "__AGENT_SERVICE_UPSTREAM_URL__",
                "/api/v1/health",
            ),
            "/agent-service/api/v1/health": (
                "__AGENT_SERVICE_UPSTREAM_URL__",
                "/api/v1/health",
            ),
            "/rag-service/health": (
                "__RAG_SERVICE_UPSTREAM_URL__",
                "/api/v1/health",
            ),
            "/rag-service/api/v1/health": (
                "__RAG_SERVICE_UPSTREAM_URL__",
                "/api/v1/health",
            ),
            "/tools-service/health": (
                "__TOOLS_SERVICE_UPSTREAM_URL__",
                "/health",
            ),
        }

        for gateway_path, (service_url, expected_upstream_path) in expected_routes.items():
            with self.subTest(gateway_path=gateway_path):
                matches = _routes_with_path(self.config, gateway_path)
                self.assertEqual(1, len(matches))
                route = matches[0]
                self.assertFalse(_has_jwt_plugin(route))
                self.assertTrue(route["strip_path"])
                self.assertEqual(["GET"], route.get("methods"))
                self.assertEqual(
                    f"{service_url}{expected_upstream_path}",
                    route["_service_url"],
                )

    def test_service_scoped_business_routes_are_protected(self) -> None:
        expected_paths = {
            "/user-service/api/v1": (
                "user-service",
                "__USER_SERVICE_UPSTREAM_URL__/api/v1",
            ),
            "/agent-service/api/v1": (
                "agent-service",
                "__AGENT_SERVICE_UPSTREAM_URL__/api/v1",
            ),
            "/rag-service/api/v1": (
                "rag-service",
                "__RAG_SERVICE_UPSTREAM_URL__/api/v1",
            ),
            "/tools-service/mcp": (
                "tools-service-mcp",
                "__TOOLS_SERVICE_UPSTREAM_URL__/mcp",
            ),
        }

        for gateway_path, (service_name, service_url) in expected_paths.items():
            with self.subTest(gateway_path=gateway_path):
                matches = _routes_with_path(self.config, gateway_path)
                self.assertEqual(1, len(matches))
                route = matches[0]
                self.assertEqual(service_name, route["_service_name"])
                self.assertEqual(service_url, route["_service_url"])
                self.assertTrue(route["strip_path"])
                self.assertTrue(_has_jwt_plugin(route))
                self.assertIsNone(route.get("methods"))

    def test_gateway_does_not_publish_unversioned_service_roots(self) -> None:
        unversioned_roots = {
            "/user-service",
            "/agent-service",
            "/rag-service",
            "/tools-service",
        }

        leaked = {
            path
            for route in _routes_by_name(self.config).values()
            for path in route.get("paths", [])
            if path in unversioned_roots
        }
        self.assertEqual(set(), leaked)

    def test_service_scoped_public_auth_and_dependency_health_routes_are_public(self) -> None:
        expected_routes = {
            "/user-service/api/v1/auth/type": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/type",
                ["GET"],
            ),
            "/user-service/api/v1/auth/login": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/login",
                ["POST"],
            ),
            "/user-service/api/v1/auth/external/login": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/external/login",
                ["POST"],
            ),
            "/user-service/api/v1/auth/logout": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/logout",
                ["POST"],
            ),
            "/user-service/api/v1/auth/refresh": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/refresh",
                ["POST"],
            ),
            "/user-service/api/v1/auth/oidc/authorize": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/oidc/authorize",
                ["GET"],
            ),
            "/user-service/api/v1/auth/oidc/callback": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/oidc/callback",
                ["GET"],
            ),
            "/user-service/api/v1/auth/register": (
                "__USER_SERVICE_UPSTREAM_URL__/api/v1/auth/register",
                ["POST"],
            ),
            "/agent-service/api/v1/auth/health": (
                "__AGENT_SERVICE_UPSTREAM_URL__/api/v1/auth/health",
                ["GET"],
            ),
            "/rag-service/api/v1/graph/health": (
                "__RAG_SERVICE_UPSTREAM_URL__/api/v1/graph/health",
                ["GET"],
            ),
        }

        for gateway_path, (service_url, methods) in expected_routes.items():
            with self.subTest(gateway_path=gateway_path):
                matches = _routes_with_path(self.config, gateway_path)
                self.assertEqual(1, len(matches))
                route = matches[0]
                self.assertFalse(_has_jwt_plugin(route))
                self.assertTrue(route["strip_path"])
                self.assertEqual(methods, route.get("methods"))
                self.assertEqual(service_url, route["_service_url"])

    def test_rag_health_has_a_public_gateway_route_without_legacy_api_rag(self) -> None:
        public_matches = _routes_with_path(self.config, "/rag-service/health")
        self.assertEqual(1, len(public_matches))
        self.assertFalse(_has_jwt_plugin(public_matches[0]))

        legacy_matches = _routes_with_path(self.config, "/api/rag")
        self.assertEqual([], legacy_matches)

    def test_internal_tools_service_route_exists_without_legacy_mcp_alias(self) -> None:
        canonical_matches = _routes_with_path(self.config, "/internal/tools-service")
        self.assertEqual(1, len(canonical_matches))
        self.assertFalse(_has_jwt_plugin(canonical_matches[0]))
        self.assertEqual("__TOOLS_SERVICE_UPSTREAM_URL__", canonical_matches[0]["_service_url"])
        self.assertTrue(canonical_matches[0]["strip_path"])
        self.assertIsNone(canonical_matches[0].get("methods"))

        legacy_matches = _routes_with_path(self.config, "/internal")
        self.assertEqual([], legacy_matches)

    def test_gateway_does_not_expose_legacy_external_routes(self) -> None:
        legacy_paths = {
            "/api/auth",
            "/api/users/internal",
            "/api/users/me/settings/internal",
            "/api/users",
            "/api/users/me/settings",
            "/api/users/me/api-keys",
            "/api/roles",
            "/api/coarse-roles",
            "/api/permissions",
            "/health",
            "/api/health",
            "/auth",
            "/api/agents",
            "/api/agent-definitions",
            "/api/agent-groups",
            "/api/admin",
            "/api/chat",
            "/api/content",
            "/api/datasources",
            "/api/federated",
            "/api/input_prompt",
            "/api/llm",
            "/api/manage",
            "/api/mcp",
            "/api/notifications",
            "/api/password",
            "/api/persona",
            "/api/proxy",
            "/api/providers",
            "/api/query",
            "/api/search",
            "/api/streaming",
            "/api/threads",
            "/api/user",
            "/api/vllm",
            "/me",
            "/settings",
            "/enterprise-settings",
            "/admin",
            "/llm",
            "/agents",
            "/assistants",
            "/threads",
            "/datasources",
            "/agent-definitions",
            "/mcp-providers",
            "/mcp-tools",
            "/search-providers",
            "/content-providers",
            "/schemas",
            "/brains",
            "/memory",
            "/collections",
            "/graph",
            "/datasources/knowledge-selector",
        }

        leaked = {
            path
            for route in _routes_by_name(self.config).values()
            for path in route.get("paths", [])
            if path in legacy_paths
        }
        self.assertEqual(set(), leaked)

    def test_internal_gateway_routes_have_service_dependency_inventory(self) -> None:
        all_routes = _routes_by_name(self.config).values()
        internal_gateway_paths = {
            path
            for route in all_routes
            for path in route.get("paths", [])
            if path.startswith("/internal")
        }
        self.assertEqual(
            set(),
            internal_gateway_paths - INTERNAL_GATEWAY_ROUTE_MATRIX.keys(),
        )

        for gateway_path, matrix_entry in INTERNAL_GATEWAY_ROUTE_MATRIX.items():
            service_name, service_url, source_root, signals = matrix_entry
            with self.subTest(gateway_path=gateway_path):
                matches = _routes_with_path(self.config, gateway_path)
                self.assertEqual(1, len(matches))
                route = matches[0]
                self.assertEqual(service_name, route["_service_name"])
                self.assertEqual(service_url, route["_service_url"])
                self.assertFalse(_has_jwt_plugin(route))
                self.assertTrue(route["strip_path"])
                self.assertTrue(_source_contains_any(source_root, signals))

    def test_web_auth_paths_are_classified_in_compatibility_matrix(self) -> None:
        discovered_auth_paths = _web_auth_paths()
        unclassified = discovered_auth_paths - PUBLIC_AUTH_COMPATIBILITY_MATRIX.keys()

        self.assertEqual(set(), unclassified)

    def test_user_service_internal_routes_match_canonical_matrix(self) -> None:
        discovered_routes = _python_route_paths(USER_SERVICE_ROUTES_ROOT)

        missing = CANONICAL_USER_INTERNAL_ROUTES - discovered_routes
        self.assertEqual(set(), missing)

    def test_user_service_internal_routes_require_internal_or_user_token(self) -> None:
        self.assertEqual([], _user_service_internal_routes_without_internal_dependency())

    def test_python_services_do_not_define_nested_api_v1_api_paths(self) -> None:
        nested_paths: list[str] = []
        for root in PYTHON_SERVICE_ROOTS:
            nested_paths.extend(
                path for path in _python_route_paths(root) if path.startswith("/api/v1/api/")
            )

        self.assertEqual([], nested_paths)


if __name__ == "__main__":
    unittest.main()
