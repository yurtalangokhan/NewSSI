"""Smoke-test the real APISIX image with disposable routing and fake credentials."""

import importlib.util
import os
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml
from check_gateway_integration import Browser, Upstream, conf_mount, repo_conf_mount

ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.environ.get("APISIX_TEST_IMAGE", "agentic-ai-platform/apisix:startup-repair")


class Echo(Upstream):
    do_POST = Upstream.do_GET  # noqa: N815 — http.server dispatches on this exact name


def main():
    spec = importlib.util.spec_from_file_location(
        "renderer", ROOT / "scripts/render_gateway_config.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    upstream = ThreadingHTTPServer(("0.0.0.0", 0), Echo)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    settings = {
        "KEYCLOAK_ISSUER_URL": "https://identity.example/realms/platform",
        "KEYCLOAK_BASE_URL": "https://identity.example",
        "KEYCLOAK_REALM": "platform",
        "KEYCLOAK_CLIENT_ID": "web",
        "GATEWAY_KEYCLOAK_CLIENT_ID": "gateway-client",
        "GATEWAY_KEYCLOAK_CLIENT_SECRET": "dummy-gateway-secret",
        "INTERNAL_SERVICE_TOKEN": "dummy-internal-secret",
        "GATEWAY_ALLOWED_REDIRECT_URIS": '["https://app.example/auth/oidc/callback"]',
        "REDIS_HOST": "redis.example",
        "REDIS_PORT": "6379",
        **{
            f"{name}_SERVICE_UPSTREAM_ADDR": f"host.docker.internal:{upstream.server_port}"
            for name in ("USER", "AGENT", "RAG", "TOOLS")
        },
    }
    config = renderer.render(
        yaml.safe_load((ROOT / "configs/apisix/apisix.yaml").read_text()), settings
    )
    name = "apisix-image-check-" + uuid.uuid4().hex[:10]
    try:
        with tempfile.TemporaryDirectory(prefix="apisix-image-") as directory:
            native = Path(directory) / "apisix.yaml"
            native.write_text(yaml.safe_dump(config, sort_keys=False) + "#END\n")
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--add-host",
                    "host.docker.internal:host-gateway",
                    "-p",
                    "127.0.0.1::8000",
                    "-e",
                    "APISIX_STAND_ALONE=true",
                    "-v",
                    conf_mount(native, "apisix.yaml"),
                    "-v",
                    repo_conf_mount("config.yaml"),
                    "-v",
                    repo_conf_mount("gateway-policies.json"),
                    IMAGE,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            address = subprocess.check_output(
                ["docker", "port", name, "8000/tcp"], text=True
            ).strip()
            url = "http://" + address
            client = Browser()
            for _ in range(40):
                try:
                    if client.call(url + "/auth/api/v1/type")[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                logs = subprocess.check_output(
                    ["docker", "logs", "--tail", "12", name], stderr=subprocess.STDOUT, text=True
                )
                raise AssertionError("APISIX did not become ready: " + logs)
            assert client.call(url + "/user-service/api/v1/users")[0] == 401
            assert client.call(url + "/internal/user-service/api/v1/users")[0] == 401
            assert client.call(url + "/internal/user-service/metrics")[0] == 404
            assert (
                client.call(
                    url + "/auth/api/v1/login", "POST", {}, {"Content-Type": "application/json"}
                )[0]
                == 400
            )
            headers = {
                "Authorization": "Bearer dummy-internal-secret",
                "x-gateway-user-id": "forged",
                "x-user-id": "delegated",
            }
            for path in (
                "/internal/user-service/api/v1/users",
                "/internal/agent-service/api/v1/internal/connector-tools/resolve",
            ):
                method = "POST" if "/agent-service/" in path else "GET"
                status, body, _ = client.call(url + path, method, headers=headers)
                assert status == 200, (path, status, body)
                assert body["path"] == path.split("-service", 1)[1]
                assert body["internal"] == "dummy-internal-secret"
                assert body["delegated"] == "delegated"
                assert body["user"] is None
            print(
                "APISIX image: native schema, auth, internal routing, spoof rejection, "
                "and metrics denial passed"
            )
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        upstream.shutdown()


if __name__ == "__main__":
    main()
