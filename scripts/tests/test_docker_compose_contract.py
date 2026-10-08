import json
import os
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from config_manager import manager as env_manager
import re
import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICES_COMPOSE_FILE = (
    REPOSITORY_ROOT / "deploy" / "docker" / "docker-compose-services.yml"
)
POSTGRES_VOLUME_TARGET = "/var/lib/postgresql"


class DockerComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose_source = SERVICES_COMPOSE_FILE.read_text(encoding="utf-8")
        cls.env_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.env_directory.cleanup)
        with mock.patch.object(env_manager, "ROOT", Path(cls.env_directory.name)):
            env_manager._shared_secret_cache.clear()
            spec = env_manager.build_specs()["configs"]
            env_manager.init_env_file(spec)
            env_file = spec.path
            text = env_file.read_text(encoding="utf-8").replace(
                "GATEWAY_ALLOWED_REDIRECT_URIS=\n",
                'GATEWAY_ALLOWED_REDIRECT_URIS=["http://localhost:3000/auth/oidc/callback"]\n',
            )
            env_file.write_text(text, encoding="utf-8")
            env_manager._shared_secret_cache.clear()
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(env_file),
                "-f",
                str(SERVICES_COMPOSE_FILE),
                "config",
                "--format",
                "json",
            ],
            check=True,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        cls.compose_model = json.loads(result.stdout)

    def test_ollama_gpu_count_uses_literal_all_in_compose_source(self) -> None:
        service_match = re.search(
            r"(?ms)^  ollama:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n)",
            self.compose_source,
        )

        self.assertIsNotNone(service_match)
        ollama_source = service_match.group("body")
        self.assertRegex(
            ollama_source,
            (
                r"(?m)^\s+- driver: nvidia\s*$\n"
                r"^\s+count: all\s*$\n"
                r"^\s+capabilities: \[gpu\]\s*$"
            ),
        )

    def test_only_ollama_has_a_gpu_device_reservation(self) -> None:
        services_with_gpu_devices = {
            service_name
            for service_name, service in self.compose_model["services"].items()
            for device in (
                service.get("deploy", {})
                .get("resources", {})
                .get("reservations", {})
                .get("devices", [])
            )
            if "gpu" in device.get("capabilities", [])
        }

        self.assertEqual({"ollama"}, services_with_gpu_devices)

    def test_ollama_uses_external_volume_and_nvidia_gpu_reservation(self) -> None:
        ollama = self.compose_model["services"]["ollama"]

        self.assertIn(
            {
                "type": "volume",
                "source": "ollama-data",
                "target": "/root/.ollama",
                "volume": {},
            },
            ollama["volumes"],
        )
        self.assertEqual(
            {"external": True, "name": "ollama"},
            self.compose_model["volumes"]["ollama-data"],
        )
        self.assertEqual(
            [
                {
                    "driver": "nvidia",
                    # Docker Compose renders the source value `all` as -1.
                    "count": -1,
                    "capabilities": ["gpu"],
                }
            ],
            ollama["deploy"]["resources"]["reservations"]["devices"],
        )

    def test_postgres_leaves_its_data_directory_to_the_image(self) -> None:
        postgres = self.compose_model["services"]["postgres"]

        self.assertIn(
            {
                "type": "volume",
                "source": "postgres-data",
                "target": POSTGRES_VOLUME_TARGET,
                "volume": {},
            },
            postgres["volumes"],
        )
        self.assertNotIn("PGDATA", postgres["environment"])

    def test_postgres_creates_no_application_database_at_init(self) -> None:
        """Each service's bootstrap creates its own database, owned by the service role.

        A database the image pre-creates belongs to the admin role, and from PostgreSQL 15
        on only the owner may create tables in its `public` schema: the service's
        migrations would fail with "permission denied for schema public".
        """
        postgres = self.compose_model["services"]["postgres"]

        self.assertNotIn("POSTGRES_DB", postgres["environment"])

    def test_postgres_does_not_start_beside_the_data_of_another_major_version(self) -> None:
        for directory, major in (("", "15"), ("pgdata", "15"), ("17/docker", "17")):
            with self.subTest(directory=directory):
                result = self.run_postgres_entrypoint({directory: major})

                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)
                self.assertIn(Path("volume", directory).as_posix(), result.stderr)
                self.assertIn("docs/deployment.md", result.stderr)

    def test_postgres_starts_on_an_empty_volume_and_on_its_own_data(self) -> None:
        for clusters in ({}, {"18/docker": "18"}, {"18/docker": "18", "pgdata": "15"}):
            with self.subTest(clusters=clusters):
                result = self.run_postgres_entrypoint(clusters)

                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("image entrypoint: postgres", result.stdout.strip())

    def test_keycloak_is_healthy_only_while_its_readiness_endpoint_answers_200(self) -> None:
        self.assertEqual(0, self.run_keycloak_health_check(200))
        self.assertNotEqual(0, self.run_keycloak_health_check(503))
        self.assertNotEqual(0, self.run_keycloak_health_check(200, listening=False))

    def test_keycloak_bootstrap_mounts_everything_the_authorization_inventory_reads(
        self,
    ) -> None:
        """The bootstrap container must compute the same inventory as the repository.

        `scripts/gateway_authorization.py` reads the services' route modules below
        /workspace; a mount that points at a directory the repository no longer has
        silently drops that service's permissions.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "gateway_authorization", REPOSITORY_ROOT / "scripts" / "gateway_authorization.py"
        )
        gateway_authorization = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gateway_authorization)
        mounts = [
            volume
            for volume in self.compose_model["services"]["keycloak-bootstrap"]["volumes"]
            if volume["type"] == "bind"
        ]
        with tempfile.TemporaryDirectory() as workspace:
            for mount in mounts:
                source = Path(mount["source"])
                self.assertTrue(source.is_dir(), f"mount source does not exist: {source}")
                target = mount["target"]
                self.assertTrue(target.startswith("/workspace/"), target)
                if target.startswith("/workspace/apps/"):
                    shutil.copytree(
                        source,
                        Path(workspace, target[len("/workspace/") :]),
                        ignore=shutil.ignore_patterns("__pycache__", ".venv", "node_modules"),
                    )
            self.assertEqual(
                gateway_authorization.inventory(REPOSITORY_ROOT),
                gateway_authorization.inventory(Path(workspace)),
            )

    def test_gateway_check_runs_the_keycloak_and_redis_images_of_the_stack(self) -> None:
        gateway_check = (
            REPOSITORY_ROOT / "scripts" / "tests" / "check_gateway_integration.py"
        ).read_text(encoding="utf-8")

        for service in ("keycloak", "redis"):
            with self.subTest(service=service):
                image = self.compose_model["services"][service]["image"]
                self.assertTrue(f'"{image}"' in gateway_check, f"it does not run {image}")

    def run_keycloak_health_check(self, status: int, *, listening: bool = True) -> int:
        """Return the exit status of the health check of the keycloak service.

        A local server stands for the management interface: it answers `status` on the
        readiness path and 404 elsewhere, or nothing listens on its port.
        """
        shell = shutil.which("bash")  # /bin/sh of the Keycloak image is bash
        if shell is None:
            self.skipTest("needs bash")
        kind, script = self.compose_model["services"]["keycloak"]["healthcheck"]["test"]
        self.assertEqual("CMD-SHELL", kind)

        class ManagementInterface(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                self.send_response(status if self.path == "/health/ready" else 404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ManagementInterface)
        port = server.server_address[1]
        if listening:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        else:
            server.server_close()
        try:
            return subprocess.run(
                [
                    shell,
                    "-c",
                    # `docker compose config` writes every `$` of the source as `$$`.
                    script.replace("$$", "$").replace("127.0.0.1/9000", f"127.0.0.1/{port}"),
                ],
                capture_output=True,
                check=False,
                timeout=30,
            ).returncode
        finally:
            if listening:
                server.shutdown()
                server.server_close()

    def run_postgres_entrypoint(
        self, clusters: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        """Run the entrypoint of the postgres service outside a container.

        The directory `volume` of a sandbox stands for the mounted volume; `clusters`
        maps a directory of that volume to the major version of the data in it. The
        entrypoint of the image is a stub that prints its arguments.
        """
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("needs a POSIX shell")
        postgres = self.compose_model["services"]["postgres"]
        _, option, script, *arguments = postgres["entrypoint"]
        with tempfile.TemporaryDirectory() as sandbox:
            Path(sandbox, "volume").mkdir()
            for directory, major in clusters.items():
                cluster = Path(sandbox, "volume", directory)
                cluster.mkdir(parents=True, exist_ok=True)
                (cluster / "PG_VERSION").write_text(f"{major}\n", encoding="utf-8")
            stub = Path(sandbox, "bin", "docker-entrypoint.sh")
            stub.parent.mkdir()
            stub.write_text(
                '#!/bin/sh\necho "image entrypoint: $*"\n', encoding="utf-8", newline="\n"
            )
            stub.chmod(0o755)
            return subprocess.run(
                [
                    shell,
                    option,
                    # `docker compose config` writes every `$` of the source as `$$`.
                    script.replace("$$", "$").replace(POSTGRES_VOLUME_TARGET, "volume"),
                    *arguments,
                    *postgres["command"],
                ],
                cwd=sandbox,
                env={
                    **os.environ,
                    "PATH": f"{stub.parent}{os.pathsep}{os.environ['PATH']}",
                    "PGDATA": "volume/18/docker",
                },
                capture_output=True,
                text=True,
                check=False,
            )


if __name__ == "__main__":
    unittest.main()
