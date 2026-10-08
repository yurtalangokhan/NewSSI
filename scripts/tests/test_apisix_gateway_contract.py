"""The APISIX gateway contract: what the edge publishes, protects and refuses.

Static checks over ``configs/apisix/apisix.yaml`` and the compose files. The
route inventory assertions carry the exposure rules of the previous gateway's
contract tests: the gateway changed, the rules did not.
"""

import ast
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
APISIX_CONFIG_FILE = ROOT / "configs" / "apisix" / "apisix.yaml"
DEPLOYMENT_DOC = ROOT / "docs" / "deployment.md"
WEB_SOURCE_ROOT = ROOT / "apps" / "web" / "src"
USER_SERVICE_ROUTES_ROOT = ROOT / "apps" / "user-service" / "src" / "api" / "routes"
PYTHON_SERVICE_ROOTS = (
    ROOT / "apps" / "user-service" / "src",
    ROOT / "apps" / "agent-service" / "src",
    ROOT / "apps" / "rag-service" / "src",
)
SERVICES = ("user-service", "rag-service", "tools-service", "agent-service")
PROTECTED_ROUTE_OF_UPSTREAM = {
    "user-service": "user-service-protected",
    "agent-service": "agent-service-protected",
    "rag-service": "rag-service-protected",
    "tools-service": "tools-service-mcp",
}

#: Internal routes: gateway prefix -> (route id, upstream, prefix rewrite, source root,
#: signals that the service really checks the shared service token).
INTERNAL_GATEWAY_ROUTE_MATRIX = {
    "/internal/user-service": (
        "internal-user-service",
        "user-service",
        ["^/internal/user-service/?(.*)", "/$1"],
        ROOT / "apps" / "user-service" / "src",
        ("require_auth_or_internal_service_token",),
    ),
    "/internal/rag-service": (
        "internal-rag-service",
        "rag-service",
        ["^/internal/rag-service/?(.*)", "/$1"],
        ROOT / "apps" / "rag-service" / "src",
        ("X-Internal-Service-Token", "internal-service", "INTERNAL_SERVICE_TOKEN"),
    ),
    "/internal/agent-service/api/v1/internal/connector-tools": (
        "internal-agent-connector-tools",
        "agent-service",
        ["^/internal/agent-service/(.*)", "/$1"],
        ROOT / "apps" / "agent-service" / "src",
        ("INTERNAL_SERVICE_TOKEN",),
    ),
    "/internal/tools-service": (
        "internal-tools-service",
        "tools-service",
        ["^/internal/tools-service/?(.*)", "/$1"],
        ROOT / "apps" / "tools-service",
        ("X-Internal-Service-Token", "INTERNAL_SERVICE_TOKEN"),
    ),
}

#: Every ``/api/auth/*`` path the web client names must be classified here.
PUBLIC_AUTH_COMPATIBILITY_MATRIX = {
    "/api/auth/type": "legacy-public",
    "/api/auth/login": "legacy-public",
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

#: The seven session endpoints the gateway-auth plugin answers itself (mode ``auth``).
AUTH_SESSION_PATHS = (
    "/user-service/api/v1/auth/type",
    "/user-service/api/v1/auth/login",
    "/user-service/api/v1/auth/external/login",
    "/user-service/api/v1/auth/logout",
    "/user-service/api/v1/auth/refresh",
    "/user-service/api/v1/auth/oidc/authorize",
    "/user-service/api/v1/auth/oidc/callback",
)

LEGACY_EXTERNAL_PATHS = {
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
    # Gateway roots and aliases that must not exist either.
    "/user-service",
    "/agent-service",
    "/rag-service",
    "/tools-service",
    "/api/rag",
    "/internal",
    "/agent-service/api/v1/auth/health",
}


# --- helpers ---------------------------------------------------------------


def _config() -> dict[str, Any]:
    return yaml.safe_load(APISIX_CONFIG_FILE.read_text(encoding="utf-8"))


def _routes(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {route["id"]: route for route in config["routes"]}


def _uris(route: dict[str, Any]) -> list[str]:
    return list(route.get("uris") or ([route["uri"]] if route.get("uri") else []))


def _routes_with_uri(config: dict[str, Any], uri: str) -> list[dict[str, Any]]:
    return [route for route in config["routes"] if uri in _uris(route)]


def _auth_mode(route: dict[str, Any]) -> str | None:
    return (route.get("plugins") or {}).get("gateway-auth", {}).get("mode")


def _terminated_with(route: dict[str, Any]) -> int | None:
    """The status the gateway answers itself (fault-injection), or ``None`` when it proxies."""
    return (
        (route.get("plugins") or {}).get("fault-injection", {}).get("abort", {}).get("http_status")
    )


def _source_contains_any(root: Path, signals: tuple[str, ...]) -> bool:
    return any(
        any(signal in path.read_text(encoding="utf-8") for signal in signals)
        for path in root.rglob("*.py")
    )


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


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
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
                prefixes[target.id] = prefix
    return prefixes


def _decorated_paths(node: ast.AST, prefixes: dict[str, str]) -> list[str]:
    paths: list[str] = []
    for decorator in getattr(node, "decorator_list", []):
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and isinstance(decorator.args[0].value, str)
        ):
            continue
        router = decorator.func.value.id if isinstance(decorator.func.value, ast.Name) else ""
        paths.append(f"{prefixes.get(router, '')}{decorator.args[0].value}")
    return paths


def _python_route_paths(source_root: Path) -> set[str]:
    paths: set[str] = set()
    for path in source_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        prefixes = _router_prefixes(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                paths.update(_decorated_paths(node, prefixes))
    return paths


def _user_service_internal_routes_without_internal_dependency() -> list[str]:
    expected = CANONICAL_USER_INTERNAL_ROUTES | {
        route.replace("/internal/users", "/users/internal", 1)
        for route in CANONICAL_USER_INTERNAL_ROUTES
    }
    missing: list[str] = []
    for path in USER_SERVICE_ROUTES_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        prefixes = _router_prefixes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            source = ast.get_source_segment(text, node) or ""
            missing.extend(
                route_path
                for route_path in _decorated_paths(node, prefixes)
                if route_path in expected and "require_auth_or_internal_service_token" not in source
            )
    return sorted(missing)


# --- compose wiring ----------------------------------------------------------


def test_apisix_compose_uses_environment_without_fallbacks():
    services = yaml.safe_load((ROOT / "deploy/docker/docker-compose-services.yml").read_text())[
        "services"
    ]
    apisix = services["apisix"]
    assert apisix["environment"]["REDIS_HOST"] == "${REDIS_HOST_CONTAINER}"
    assert ":?" in apisix["environment"]["GATEWAY_KEYCLOAK_CLIENT_ID"]
    assert ":?" in apisix["environment"]["GATEWAY_KEYCLOAK_CLIENT_SECRET"]


def test_apisix_is_the_only_active_gateway():
    services = yaml.safe_load((ROOT / "deploy/docker/docker-compose-services.yml").read_text())[
        "services"
    ]
    assert "kong" not in services
    assert "apisix" in services
    assert services["apisix"]["build"]["dockerfile"] == "configs/apisix/Dockerfile"


def test_apisix_receives_external_keycloak_settings():
    services = yaml.safe_load((ROOT / "deploy/docker/docker-compose-services.yml").read_text())[
        "services"
    ]
    environment = services["apisix"]["environment"]
    assert environment["EXTERNAL_KEYCLOAK"] == "${EXTERNAL_KEYCLOAK}"
    assert environment["EXTERNAL_KEYCLOAK_ALIAS"] == "${EXTERNAL_KEYCLOAK_ALIAS}"


def test_container_service_calls_use_apisix():
    for mode in ("dev", "prod"):
        text = (ROOT / f"deploy/docker/docker-compose-{mode}.yml").read_text()
        assert "http://kong:" not in text
        assert "http://apisix:8000/internal/tools-service/mcp" in text


# --- route inventory -----------------------------------------------------------


def test_every_route_has_a_unique_id_and_name():
    config = _config()
    ids = [route["id"] for route in config["routes"]]
    names = [route.get("name") for route in config["routes"]]
    assert all(names), "an unnamed route cannot be told apart in the admin API and the logs"
    assert len(set(ids)) == len(ids) and len(set(names)) == len(names)


def test_no_route_is_shadowed_by_another_on_the_same_uri():
    """Two routes on one URI resolve by priority; the loser is dead configuration."""
    config = _config()
    seen: dict[str, str] = {}
    for route in config["routes"]:
        for uri in _uris(route):
            assert uri not in seen, f"{route['id']} and {seen[uri]} both claim {uri}"
            seen[uri] = route["id"]


def test_apisix_protects_internal_and_user_routes():
    routes = _routes(_config())
    for name in (
        "user-service-protected",
        "agent-service-protected",
        "rag-service-protected",
        "tools-service-mcp",
    ):
        assert routes[name]["plugins"]["gateway-auth"]["mode"] == "protected"
        assert "openid-connect" not in routes[name]["plugins"]
    for name in (
        "internal-user-service",
        "internal-rag-service",
        "internal-tools-service",
        "internal-agent-connector-tools",
    ):
        assert routes[name]["plugins"]["gateway-auth"]["mode"] == "internal"
    assert routes["gateway-auth"]["plugins"]["gateway-auth"]["mode"] == "auth"
    # Connector syncs run inside agent-service: nothing outside calls an ingest route.
    assert not any("/ingest" in uri for route in routes.values() for uri in _uris(route))


@pytest.mark.parametrize(
    ("gateway_path", "upstream", "upstream_path"),
    [
        ("/user-service/health", "user-service", "/api/v1/health"),
        ("/user-service/api/v1/health", "user-service", "/api/v1/health"),
        ("/user-service/health/ready", "user-service", "/api/v1/health/ready"),
        ("/user-service/api/v1/health/ready", "user-service", "/api/v1/health/ready"),
        ("/agent-service/health", "agent-service", "/api/v1/health"),
        ("/agent-service/api/v1/health", "agent-service", "/api/v1/health"),
        ("/rag-service/health", "rag-service", "/api/v1/health"),
        ("/rag-service/api/v1/health", "rag-service", "/api/v1/health"),
        ("/rag-service/api/v1/graph/health", "rag-service", "/api/v1/graph/health"),
        ("/tools-service/health", "tools-service", "/health"),
    ],
)
def test_service_scoped_health_routes_are_public(gateway_path, upstream, upstream_path):
    config = _config()
    [route] = _routes_with_uri(config, gateway_path)
    assert _auth_mode(route) is None, "health is read without a token"
    assert route["methods"] == ["GET"]
    assert route["upstream_id"] == upstream
    assert route["plugins"]["proxy-rewrite"]["uri"] == upstream_path
    # Ahead of the protected catch-all of the same service, which would demand a token.
    protected = PROTECTED_ROUTE_OF_UPSTREAM[upstream]
    assert route["priority"] > _routes(config)[protected]["priority"]


@pytest.mark.parametrize(
    ("route_id", "prefix", "upstream"),
    [
        ("user-service-protected", "/user-service/api/v1", "user-service"),
        ("agent-service-protected", "/agent-service/api/v1", "agent-service"),
        ("rag-service-protected", "/rag-service/api/v1", "rag-service"),
        ("tools-service-mcp", "/tools-service/mcp", "tools-service"),
    ],
)
def test_service_scoped_business_routes_are_protected(route_id, prefix, upstream):
    route = _routes(_config())[route_id]
    assert _uris(route) == [prefix, f"{prefix}/*"]
    assert route.get("methods") is None, "every method of the API goes through the policy"
    assert route["upstream_id"] == upstream
    assert _auth_mode(route) == "protected"
    # The gateway prefix is stripped: the service sees its own /api/v1 (or /mcp) path.
    assert route["plugins"]["proxy-rewrite"]["regex_uri"] == [f"^/{upstream}/(.*)", "/$1"]


def test_streaming_routes_keep_long_timeouts_and_no_buffering():
    routes = _routes(_config())
    for route_id in ("agent-service-protected", "tools-service-mcp", "internal-tools-service"):
        route = routes[route_id]
        assert route["timeout"]["read"] == 600 and route["timeout"]["send"] == 600
        assert "proxy-buffering" in route["plugins"]


def test_session_auth_endpoints_are_answered_by_the_gateway():
    """The gateway-auth plugin in ``auth`` mode serves login, refresh, logout and the
    OIDC flow itself; user-service never sees these paths."""
    routes = _routes(_config())
    session = routes["user-auth-session"]
    assert sorted(_uris(session)) == sorted(AUTH_SESSION_PATHS)
    assert _auth_mode(session) == "auth" and session.get("methods") is None
    canonical = routes["gateway-auth"]
    assert (
        _uris(canonical) == ["/auth/api/v1", "/auth/api/v1/*"] and _auth_mode(canonical) == "auth"
    )
    for path in AUTH_SESSION_PATHS:
        assert _routes_with_uri(_config(), path) == [session], (
            f"{path} must be served once, by the plugin"
        )
    # Both auth routes win over the protected catch-all of the same service.
    assert session["priority"] > routes["user-service-protected"]["priority"]
    assert canonical["priority"] > routes["user-service-protected"]["priority"]


def test_register_is_public_and_proxied_to_user_service():
    [route] = _routes_with_uri(_config(), "/user-service/api/v1/auth/register")
    assert route["id"] == "user-auth-register"
    assert _auth_mode(route) is None and route["methods"] == ["POST"]
    assert route["upstream_id"] == "user-service"
    assert route["plugins"]["proxy-rewrite"]["uri"] == "/api/v1/auth/register"
    assert route["priority"] > _routes(_config())["user-auth-session"]["priority"]


def test_gateway_does_not_expose_legacy_or_unversioned_paths():
    config = _config()
    leaked = {
        uri for route in config["routes"] for uri in _uris(route) if uri in LEGACY_EXTERNAL_PATHS
    }
    assert leaked == set()


def test_internal_gateway_routes_have_service_dependency_inventory():
    config = _config()
    internal_uris = {
        uri.removesuffix("/*")
        for route in config["routes"]
        if _terminated_with(route) is None
        for uri in _uris(route)
        if uri.startswith("/internal")
    }
    assert internal_uris == set(INTERNAL_GATEWAY_ROUTE_MATRIX), (
        "an internal route without an inventory entry"
    )

    routes = _routes(config)
    for gateway_path, (
        route_id,
        upstream,
        regex_uri,
        source_root,
        signals,
    ) in INTERNAL_GATEWAY_ROUTE_MATRIX.items():
        route = routes[route_id]
        assert _uris(route) == [gateway_path, f"{gateway_path}/*"]
        assert route["upstream_id"] == upstream
        assert _auth_mode(route) == "internal"
        assert route["plugins"]["proxy-rewrite"]["regex_uri"] == regex_uri
        assert _source_contains_any(source_root, signals), (
            f"{upstream} does not check the service token"
        )


def test_metrics_paths_are_terminated_with_404_before_any_internal_route():
    """The Prometheus endpoint must not be reachable through the gateway.

    The ``internal-*`` routes forward a service root, so ``/internal/<service>/metrics``
    would otherwise reach the service's ``/metrics``. Metrics are scraped on the pod
    network; publishing them at the edge leaks route names, volumes and error rates.
    """
    config = _config()
    routes = _routes(config)
    deny = routes["operational-endpoints-denied"]
    assert _terminated_with(deny) == 404
    for service in SERVICES:
        for prefix in (f"/internal/{service}", f"/{service}"):
            assert f"{prefix}/metrics" in _uris(deny), f"{prefix}/metrics is not denied"
    # Denied before the catch-alls that would forward it.
    assert deny["priority"] > max(
        routes[name]["priority"]
        for name in ("internal-user-service", "internal-rag-service", "internal-tools-service")
    )
    assert deny["priority"] > routes["internal-agent-connector-tools"]["priority"]


def test_upstreams_connect_fast_and_keep_the_node_host():
    config = _config()
    for upstream in config["upstreams"]:
        assert upstream["timeout"]["connect"] == 5, (
            "a down service is noticed in seconds, not a minute"
        )
        assert upstream["pass_host"] == "node", "no backend reads Host or X-Forwarded-*"
    long_read = {u["id"]: u["timeout"]["read"] for u in config["upstreams"]}
    assert long_read["agent-service"] == 600 and long_read["tools-service"] == 600


def test_deployment_doc_states_the_edge_proxy_contract():
    """Operators read the connect timeout, retry and Host behaviour from docs/deployment.md."""
    text = DEPLOYMENT_DOC.read_text(encoding="utf-8")
    connect = {u["timeout"]["connect"] for u in _config()["upstreams"]}
    documented = re.search(r"connection within (\d+) s\b", text)
    assert documented and {int(documented.group(1))} == connect
    claims = (
        "`retries` is not",
        "`pass_host: node`",
        "`proxy_request_buffering off`",
        "`proxy-buffering`",
    )
    for claim in claims:
        assert claim in text, claim


# --- the services behind the gateway ----------------------------------------------


def test_web_auth_paths_are_classified_in_compatibility_matrix():
    assert _web_auth_paths() - PUBLIC_AUTH_COMPATIBILITY_MATRIX.keys() == set()


def test_user_service_internal_routes_match_canonical_matrix():
    assert CANONICAL_USER_INTERNAL_ROUTES - _python_route_paths(USER_SERVICE_ROUTES_ROOT) == set()


def test_user_service_internal_routes_require_internal_or_user_token():
    assert _user_service_internal_routes_without_internal_dependency() == []


def test_python_services_do_not_define_nested_api_v1_api_paths():
    nested = [
        path
        for root in PYTHON_SERVICE_ROOTS
        for path in _python_route_paths(root)
        if path.startswith("/api/v1/api/")
    ]
    assert nested == []


# --- renderer ------------------------------------------------------------------------


def test_apisix_native_addresses_and_secret_contract():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gateway_renderer", ROOT / "scripts/render_gateway_config.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    settings = {
        "KEYCLOAK_ISSUER_URL": "https://identity.example/realms/test",
        "KEYCLOAK_BASE_URL": "https://identity.example",
        "KEYCLOAK_REALM": "test",
        "KEYCLOAK_CLIENT_ID": "web",
        "GATEWAY_KEYCLOAK_CLIENT_ID": "gateway-client",
        "GATEWAY_KEYCLOAK_CLIENT_SECRET": "secret'\n:value",
        "INTERNAL_SERVICE_TOKEN": "machine-secret",
        "REDIS_HOST": "redis",
        "REDIS_PORT": "6379",
        "GATEWAY_ALLOWED_REDIRECT_URIS": '["https://app.example/auth/oidc/callback"]',
        **{
            f"{name}_SERVICE_UPSTREAM_ADDR": f"{name.lower()}:8080"
            for name in ("USER", "AGENT", "RAG", "TOOLS")
        },
    }
    template = _config()
    rendered = renderer.render(template, settings)
    assert rendered["upstreams"][0]["nodes"] == {"user:8080": 1}
    auth = next(route for route in rendered["routes"] if route["id"] == "gateway-auth")["plugins"][
        "gateway-auth"
    ]
    assert auth["introspection_client_id"] == "gateway-client"
    assert auth["introspection_client_secret"] == "secret'\n:value"
    for invalid in (
        "user",
        "http://user:8080",
        "user:8080/path",
        "user:bad",
        "name:secret@user:80",
    ):
        with pytest.raises(ValueError, match="UPSTREAM_ADDR"):
            renderer.render(template, {**settings, "USER_SERVICE_UPSTREAM_ADDR": invalid})
