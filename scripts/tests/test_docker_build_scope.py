"""Push gate rebuilds exactly the service images whose build inputs changed."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
LIB = "scripts/quality/lib/docker_services.sh"
COMPOSE_FILE = "deploy/docker/docker-compose-dev.yml"
SERVICES = ("agent-service", "rag-service", "user-service", "tools-service")
ALL_SERVICES = " ".join(SERVICES)


def run_lib(
    command: str, stdin: str = "", cwd: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"source {LIB} && {command}"],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def affected_services(*files: str) -> str:
    result = run_lib("quality_docker_services", "\n".join(files) + "\n")
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class DockerBuildScopeTests(unittest.TestCase):
    def test_files_outside_every_image_rebuild_nothing(self) -> None:
        self.assertEqual(
            affected_services(
                "scripts/quality/fix.sh",
                "docs/developer-guide.md",
                "apps/agent-service/tests/test_app.py",
            ),
            "",
        )

    def test_shared_package_rebuilds_only_services_that_copy_it(self) -> None:
        self.assertEqual(
            affected_services("packages/security/src/resilience/retry.py"),
            "agent-service",
        )
        self.assertEqual(
            affected_services("packages/security/src/secrets_py/vault.py"),
            "agent-service user-service",
        )

    def test_service_files_copied_into_its_image_rebuild_it(self) -> None:
        self.assertEqual(
            affected_services(
                "apps/tools-service/server.py",
                "apps/rag-service/src/server.py",
                "apps/user-service/locales/tr.json",
            ),
            "rag-service user-service tools-service",
        )

    def test_service_dockerfile_rebuilds_that_service(self) -> None:
        self.assertEqual(
            affected_services("apps/agent-service/docker/Dockerfile.service"),
            "agent-service",
        )

    def test_shared_build_config_rebuilds_every_service(self) -> None:
        for changed in (
            "deploy/docker/docker-compose-dev.yml",
            ".dockerignore",
            "Makefile",
        ):
            with self.subTest(changed=changed):
                self.assertEqual(affected_services(changed), ALL_SERVICES)

    def test_dockerfile_paths_match_the_compose_build_definitions(self) -> None:
        compose_path = ROOT / COMPOSE_FILE
        services = yaml.safe_load(compose_path.read_text())["services"]

        for service in SERVICES:
            with self.subTest(service=service):
                build = services[service]["build"]
                context = (compose_path.parent / build["context"]).resolve()
                expected = (context / build.get("dockerfile", "Dockerfile")).relative_to(
                    ROOT
                )
                result = run_lib(f"quality_service_dockerfile {service}")

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(expected))


class DockerfileResolutionTests(unittest.TestCase):
    """Compose drift must be followed or fail the gate, never be skipped."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.repo = Path(self._temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / LIB).parent.mkdir(parents=True)
        shutil.copy2(ROOT / LIB, self.repo / LIB)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def write_compose(self, **dockerfiles: str) -> None:
        blocks = "".join(
            f"  {service}:\n    build:\n      context: ../..\n"
            f"      dockerfile: {dockerfile}\n    image: example/{service}\n"
            for service, dockerfile in dockerfiles.items()
        )
        self.write(COMPOSE_FILE, f"name: example\nservices:\n{blocks}networks:\n  default:\n")

    def default_dockerfiles(self) -> dict[str, str]:
        dockerfiles = {service: f"apps/{service}/Dockerfile" for service in SERVICES}
        for path in dockerfiles.values():
            self.write(path, "FROM scratch\n")
        return dockerfiles

    def test_renamed_dockerfile_in_compose_is_followed(self) -> None:
        dockerfiles = self.default_dockerfiles()
        dockerfiles["agent-service"] = "apps/agent-service/build/Dockerfile.api"
        self.write(
            dockerfiles["agent-service"],
            "FROM scratch\nCOPY packages/only-agent/ /app/packages/only-agent/\n",
        )
        self.write_compose(**dockerfiles)

        result = run_lib(
            "quality_docker_services", "packages/only-agent/x.py\n", cwd=self.repo
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "agent-service")

    def test_missing_dockerfile_fails_instead_of_skipping(self) -> None:
        dockerfiles = self.default_dockerfiles()
        dockerfiles["rag-service"] = "apps/rag-service/Dockerfile.gone"
        self.write_compose(**dockerfiles)

        result = run_lib("quality_docker_services", "README.md\n", cwd=self.repo)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertIn("rag-service", result.stderr)

    def test_service_absent_from_compose_fails(self) -> None:
        dockerfiles = self.default_dockerfiles()
        del dockerfiles["tools-service"]
        self.write_compose(**dockerfiles)

        result = run_lib("quality_docker_services", "Makefile\n", cwd=self.repo)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tools-service", result.stderr)


if __name__ == "__main__":
    unittest.main()
