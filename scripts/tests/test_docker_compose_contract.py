import json
import re
import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPOSITORY_ROOT / "configs" / ".env"
SERVICES_COMPOSE_FILE = (
    REPOSITORY_ROOT / "configs" / "docker-compose-services.yml"
)


class DockerComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose_source = SERVICES_COMPOSE_FILE.read_text(encoding="utf-8")
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(ENV_FILE),
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


if __name__ == "__main__":
    unittest.main()
