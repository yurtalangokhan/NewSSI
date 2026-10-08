"""Exercise Gateway against disposable Keycloak/Redis; never use the running stack."""

import ast
import asyncio
import contextlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)

import yaml

ROOT = Path(__file__).resolve().parents[2]
APISIX_CONF_DIR = "/usr/local/apisix/conf"


def conf_mount(host_path: Path, filename: str) -> str:
    """Read-only bind mount of ``host_path`` as ``filename`` in the APISIX conf dir."""
    return f"{host_path.as_posix()}:{APISIX_CONF_DIR}/{filename}:ro"


def repo_conf_mount(filename: str) -> str:
    """Mount the checked-in ``configs/apisix/<filename>`` under its own name."""
    return conf_mount(ROOT / "configs/apisix" / filename, filename)


#: Client ids of the platform services, as the deployment names them
#: (``docs/env-variables.md``): ``<service>-service-client``.
SERVICE_CLIENT_IDS = {
    service: f"{service.lower()}-service-client" for service in ("USER", "AGENT", "RAG", "TOOLS")
}

sys.path.insert(0, str(ROOT / "scripts"))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class Browser:
    def __init__(self):
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies), NoRedirect())

    def call(self, url, method="GET", data=None, headers=None):
        headers = dict(headers or {})
        if data is not None and headers.get("Content-Type") == "application/json":
            data = json.dumps(data).encode()
        elif isinstance(data, dict):
            data = urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        body = response.read().decode()
        with contextlib.suppress(ValueError):
            body = json.loads(body)
        return response.status, body, response.headers


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "path": self.path,
                    "user": self.headers.get("x-gateway-user-id"),
                    "internal": self.headers.get("x-internal-service-token"),
                    "alias": self.headers.get("x-internal-token"),
                    "delegated": self.headers.get("x-user-id"),
                }
            ).encode()
        )

    def log_message(self, *args):
        pass


class LoginForm(HTMLParser):
    action = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs["action"]


def docker(*args):
    result = subprocess.run(["docker", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def wait_ready(url):
    browser = Browser()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if browser.call(url)[0] == 200:
                return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    raise AssertionError("Disposable service readiness timed out")


def main():
    from bootstrap_gateway_authorization import AdminClient, bootstrap

    spec = importlib.util.spec_from_file_location(
        "renderer", ROOT / "scripts/render_gateway_config.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    prefix = "gateway-check-" + uuid.uuid4().hex[:10]
    containers = []
    upstream = ThreadingHTTPServer(("0.0.0.0", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    docker("network", "create", prefix)
    try:
        kc_name, redis_name, gateway_name = (
            prefix + "-kc",
            prefix + "-redis",
            prefix + "-proxy",
        )
        issuer = f"http://{kc_name}:8080/realms/platform"
        docker(
            "run",
            "-d",
            "--name",
            kc_name,
            "--network",
            prefix,
            "-p",
            "127.0.0.1::8080",
            "-e",
            "KC_BOOTSTRAP_ADMIN_USERNAME=admin",
            "-e",
            "KC_BOOTSTRAP_ADMIN_PASSWORD=DisposableAdmin123!",
            "quay.io/keycloak/keycloak:26.8",
            "start-dev",
            "--hostname",
            f"http://{kc_name}:8080",
        )
        containers.append(kc_name)
        kc_base = "http://" + docker("port", kc_name, "8080/tcp")
        wait_ready(kc_base + "/realms/master/.well-known/openid-configuration")
        browser = Browser()
        code, token, _ = browser.call(
            kc_base + "/realms/master/protocol/openid-connect/token",
            "POST",
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "admin",
                "password": "DisposableAdmin123!",
            },
        )
        assert code == 200, "Disposable admin login failed"
        admin_headers = {
            "Authorization": "Bearer " + token["access_token"],
            "Content-Type": "application/json",
        }

        def admin(path, method="GET", data=None):
            status, body, _ = browser.call(
                kc_base + "/admin/realms" + path, method, data, admin_headers
            )
            assert 200 <= status < 300, f"Seed admin operation failed: {method} {path}: {status}"
            return body

        admin(
            "",
            "POST",
            {
                "realm": "platform",
                "enabled": True,
                "revokeRefreshToken": True,
                "sslRequired": "none",
            },
        )
        admin(
            "/platform/clients",
            "POST",
            {
                "clientId": "web",
                "enabled": True,
                "publicClient": True,
                "protocol": "openid-connect",
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": True,
                "redirectUris": ["http://app.example/auth/oidc/callback"],
            },
        )
        # One confidential client per platform service, named as the deployment
        # names them (``KEYCLOAK_<SERVICE>_SERVICE_CLIENT_ID``); the authorization
        # bootstrap below manages exactly these.
        for client_id in SERVICE_CLIENT_IDS.values():
            admin(
                "/platform/clients",
                "POST",
                {
                    "clientId": client_id,
                    "enabled": True,
                    "publicClient": False,
                    "serviceAccountsEnabled": True,
                    "protocol": "openid-connect",
                },
            )
        service = admin(f"/platform/clients?clientId={SERVICE_CLIENT_IDS['USER']}")[0]
        admin(
            f"/platform/clients/{service['id']}/roles",
            "POST",
            {"name": "user:list", "attributes": {"agentic.permissions": ["user:list"]}},
        )
        role = admin(f"/platform/clients/{service['id']}/roles/user:list")
        for name in ("allowed", "denied"):
            admin(
                "/platform/users",
                "POST",
                {
                    "username": name,
                    "enabled": True,
                    "email": name + "@example.com",
                    "emailVerified": True,
                    "firstName": name,
                    "lastName": "Test",
                    "credentials": [
                        {
                            "type": "password",
                            "value": "DisposableUser123!",
                            "temporary": False,
                        }
                    ],
                },
            )
        allowed_user = admin("/platform/users?username=allowed")[0]
        admin(
            f"/platform/users/{allowed_user['id']}/role-mappings/clients/{service['id']}",
            "POST",
            [role],
        )
        os.environ.update(
            {
                "KEYCLOAK_BASE_URL": kc_base,
                "KEYCLOAK_REALM": "platform",
                "KEYCLOAK_CLIENT_ID": "web",
                "GATEWAY_KEYCLOAK_CLIENT_ID": "gateway-client",
                "GATEWAY_KEYCLOAK_CLIENT_SECRET": "dummy-gateway-secret",
                **{
                    f"KEYCLOAK_{service}_SERVICE_CLIENT_ID": client_id
                    for service, client_id in SERVICE_CLIENT_IDS.items()
                },
                "KEYCLOAK_BOOTSTRAP_ADMIN_TOKEN": token["access_token"],
                "KEYCLOAK_ADMIN": "admin",
                "KEYCLOAK_ADMIN_PASSWORD": "DisposableAdmin123!",
            }
        )
        asyncio.run(bootstrap(AdminClient()))
        # Exercise the production pure instance-policy builder without importing SQL runtime.
        source = ROOT / "apps/user-service/src/repository/keycloak_resource_authorization.py"
        tree = ast.parse(source.read_text())
        selected = [
            node
            for node in tree.body
            if (isinstance(node, ast.FunctionDef) and node.name == "instance_authorization_objects")
            or (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id in {"INSTANCE_POLICY_PREFIX", "PERMISSION_LEVELS"}
                    for target in node.targets
                )
            )
        ]
        namespace = {"Any": Any}
        # Execute only the repository's allowlisted pure builder and constant AST nodes.
        exec(  # noqa: S102
            compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"),
            namespace,
        )
        admin("/platform/groups", "POST", {"name": "instance-readers"})
        group = admin("/platform/groups?search=instance-readers")[0]
        admin(f"/platform/users/{allowed_user['id']}/groups/{group['id']}", "PUT")
        objects = namespace["instance_authorization_objects"](
            [
                {
                    "resource_type": "agent",
                    "resource_id": "agent-1",
                    "user_id": None,
                    "organization_id": group["id"],
                    "permission_level": "read",
                }
            ],
            "agent",
        )
        agent_client = admin(f"/platform/clients?clientId={SERVICE_CLIENT_IDS['AGENT']}")[0]
        instance_base = f"/platform/clients/{agent_client['id']}/authz/resource-server"
        for resource in objects["resources"]:
            admin(instance_base + "/resource", "POST", resource)
        for policy in objects["policies"]:
            admin(instance_base + "/policy/" + policy["type"], "POST", policy)
        resources = {row["name"]: row["_id"] for row in admin(instance_base + "/resource?max=-1")}
        policies = {row["name"]: row["id"] for row in admin(instance_base + "/policy?max=-1")}
        for permission in objects["permissions"]:
            admin(
                instance_base + "/permission/scope",
                "POST",
                {
                    **permission,
                    "resources": [resources[name] for name in permission["resources"]],
                    "policies": [policies[name] for name in permission["policies"]],
                },
            )
        docker("run", "-d", "--name", redis_name, "--network", prefix, "redis:8.10-alpine")
        containers.append(redis_name)
        settings = {
            **os.environ,
            "GATEWAY_KEYCLOAK_CLIENT_ID": "gateway-client",
            "GATEWAY_KEYCLOAK_CLIENT_SECRET": "dummy-gateway-secret",
            "KEYCLOAK_ISSUER_URL": issuer,
            "GATEWAY_KEYCLOAK_REALM_URL": issuer,
            "INTERNAL_SERVICE_TOKEN": "dummy-internal-secret",
            "GATEWAY_ALLOWED_REDIRECT_URIS": '["http://app.example/auth/oidc/callback"]',
            "GATEWAY_COOKIE_SECURE": "false",
            "REDIS_HOST": redis_name,
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "",
            "KEYCLOAK_CLIENT_SECRET": "",
            "GATEWAY_EXTERNAL_IDP_ALIAS": "",
            **{
                f"{name}_SERVICE_UPSTREAM_ADDR": f"host.docker.internal:{upstream.server_port}"
                for name in ("USER", "AGENT", "RAG", "TOOLS")
            },
        }
        config = renderer.render(
            yaml.safe_load((ROOT / "configs/apisix/apisix.yaml").read_text()), settings
        )
        with tempfile.TemporaryDirectory(prefix="gateway-live-") as directory:
            Path(directory, "apisix.yaml").write_text(
                yaml.safe_dump(config, sort_keys=False) + "#END\n"
            )
            docker(
                "run",
                "-d",
                "--name",
                gateway_name,
                "--network",
                prefix,
                "--add-host",
                "host.docker.internal:host-gateway",
                "-p",
                "127.0.0.1::8000",
                "-e",
                "APISIX_STAND_ALONE=true",
                "-v",
                conf_mount(Path(directory) / "apisix.yaml", "apisix.yaml"),
                "-v",
                repo_conf_mount("config.yaml"),
                "-v",
                repo_conf_mount("gateway-policies.json"),
                os.environ.get("APISIX_TEST_IMAGE", "agentic-ai-platform/apisix:startup-repair"),
            )
            containers.append(gateway_name)
            gateway = "http://" + docker("port", gateway_name, "8000/tcp")
            wait_ready(gateway + "/auth/api/v1/type")
            session = Browser()
            status, tokens, headers = session.call(
                gateway + "/auth/api/v1/login",
                "POST",
                {"username": "allowed", "password": "DisposableUser123!"},
            )
            assert status == 200, f"Gateway login failed: {status} {tokens}"
            assert tokens["data"]["user"]["id"] == allowed_user["id"]
            assert len(headers.get_all("Set-Cookie")) >= 2
            user_headers = {"Authorization": "Bearer " + tokens["data"]["access_token"]}
            assert (
                Browser().call(gateway + "/user-service/api/v1/users", headers=user_headers)[0]
                == 200
            ), "UMA allow failed"
            assert (
                Browser().call(
                    gateway + "/user-service/api/v1/not-in-inventory",
                    headers=user_headers,
                )[0]
                == 403
            )
            assert (
                Browser().call(
                    gateway + "/user-service/api/v1/users",
                    headers={"Authorization": "Bearer invalid"},
                )[0]
                == 401
            )
            denied = Browser()
            status, denied_tokens, _ = denied.call(
                gateway + "/auth/api/v1/login",
                "POST",
                {"username": "denied", "password": "DisposableUser123!"},
            )
            assert status == 200
            denied_headers = {"Authorization": "Bearer " + denied_tokens["data"]["access_token"]}
            assert (
                Browser().call(gateway + "/user-service/api/v1/users", headers=denied_headers)[0]
                == 403
            ), "UMA deny failed"
            instance_form = {
                "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
                "audience": SERVICE_CLIENT_IDS["AGENT"],
                "permission": "agent:agent-1#read",
                "response_mode": "decision",
            }
            decision_url = kc_base + "/realms/platform/protocol/openid-connect/token"
            status, decision, _ = Browser().call(decision_url, "POST", instance_form, user_headers)
            assert status == 200 and decision["result"] is True, "Instance group grant denied"
            assert Browser().call(decision_url, "POST", instance_form, denied_headers)[0] == 403, (
                "Instance group nonmember allowed"
            )
            admin(f"/platform/users/{allowed_user['id']}/groups/{group['id']}", "DELETE")
            assert Browser().call(decision_url, "POST", instance_form, user_headers)[0] == 403, (
                "Removed group member retained instance access"
            )
            internal_url = gateway + "/internal/user-service/api/v1/users"
            assert (
                Browser().call(
                    internal_url,
                    headers={
                        **denied_headers,
                        "X-Internal-Service-Token": "dummy-internal-secret",
                    },
                )[0]
                == 403
            )
            status, body, _ = Browser().call(
                internal_url,
                headers={
                    **user_headers,
                    "X-Internal-Service-Token": "dummy-internal-secret",
                },
            )
            assert status == 200 and body["internal"] is None, "Internal bearer enforcement failed"
            assert (
                Browser().call(
                    internal_url,
                    headers={"X-Internal-Service-Token": "dummy-internal-secret"},
                )[0]
                == 200
            )
            status, machine, _ = Browser().call(
                internal_url,
                headers={
                    "Authorization": "Bearer dummy-internal-secret",
                    "X-Internal-Token": "dummy-internal-secret",
                    "X-User-Id": "delegated-user",
                },
            )
            assert (
                status == 200
                and machine["delegated"] == "delegated-user"
                and machine["alias"] == "dummy-internal-secret"
            )
            assert (
                Browser().call(
                    internal_url,
                    headers={
                        **denied_headers,
                        "X-Internal-Token": "dummy-internal-secret",
                    },
                )[0]
                == 403
            )
            assert session.call(gateway + "/auth/api/v1/refresh", "POST")[0] == 200
            assert session.call(gateway + "/auth/api/v1/logout", "POST")[0] == 200
            assert session.call(gateway + "/auth/api/v1/refresh", "POST")[0] == 401
            # Complete real browser authorization-code + PKCE flow through Redis state.
            oidc = Browser()
            status, authorization, _ = oidc.call(
                gateway
                + "/auth/api/v1/oidc/authorize?"
                + urlencode({"redirect_uri": "http://app.example/auth/oidc/callback"})
            )
            assert status == 200

            def local_identity_url(url):
                parts = urlsplit(url)
                return urlunsplit(("http", urlsplit(kc_base).netloc, parts.path, parts.query, ""))

            # Keep the public Host while transporting via Docker's loopback port.
            # Keycloak treats a loopback Host as a secure context and issues Secure
            # cookies, which Python's non-browser CookieJar will not send over HTTP.
            identity_headers = {"Host": urlsplit(issuer).netloc}
            status, html, _ = oidc.call(
                local_identity_url(authorization["data"]["authorization_url"]),
                headers=identity_headers,
            )
            assert status == 200
            form = LoginForm()
            form.feed(html)
            assert form.action, "Keycloak login form missing"
            status, login_result, redirect = oidc.call(
                local_identity_url(form.action),
                "POST",
                {
                    "username": "allowed",
                    "password": "DisposableUser123!",
                    "credentialId": "",
                },
                identity_headers,
            )
            feedback = [
                re.sub(r"<[^>]*>", "", value).strip()
                for value in re.findall(
                    r"<(?:p|span|h1)[^>]*>(.*?)</(?:p|span|h1)>",
                    str(login_result),
                    re.DOTALL,
                )
            ][:12]
            feedback.append("cookies=" + ",".join(cookie.name for cookie in oidc.cookies))
            assert status == 302, f"Keycloak browser login did not redirect: {status} {feedback}"
            query = parse_qs(urlsplit(redirect["Location"]).query)
            callback = (
                gateway
                + "/auth/api/v1/oidc/callback?"
                + urlencode(
                    {
                        "code": query["code"][0],
                        "state": query["state"][0],
                        "redirect_uri": "http://app.example/auth/oidc/callback",
                    }
                )
            )
            status, result, _ = oidc.call(callback)
            assert status == 200, f"OIDC callback failed: {status} {result}"
            assert oidc.call(callback)[0] == 401, "OIDC replay accepted"
            assert oidc.call(gateway + "/auth/api/v1/logout", "POST")[0] == 200
            print(
                "Gateway real Keycloak/Redis login, UMA allow/deny, refresh/logout, "
                "internal routing and OIDC PKCE passed"
            )
    finally:
        for name in reversed(containers):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        subprocess.run(["docker", "network", "rm", prefix], capture_output=True, check=False)
        upstream.shutdown()


if __name__ == "__main__":
    main()
