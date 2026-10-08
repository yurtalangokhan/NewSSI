"""Infrastructure ports must not be published on all interfaces.

Parses the compose files with plain line-scanning rather than a YAML
dependency: both files use a flat, hand-written two-space indentation, and
a full YAML parser is not otherwise needed anywhere in this tool -- see
env_manager.py, which is stdlib-only apart from the optional
`cryptography` import it already tolerates missing.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "deploy" / "docker" / "docker-compose-services.yml"
PROD = ROOT / "deploy" / "docker" / "docker-compose-prod.yml"

# The gateway's listeners are owned by the gateway workstream; see spec
# Appendix A. It is the edge, so it is the one service meant to be published.
# Every other published infrastructure port binds through a per-service
# address key that the central catalog (config_manager manager.py) defaults to
# 127.0.0.1: a developer machine exposes nothing, a shared server that
# developers reach remotely widens exactly the services it means to. The
# inline `:-127.0.0.1` fallback keeps an env file without the key safe.
EXEMPT_SERVICES = {"apisix"}
BIND_ADDRESS_KEYS = {
    "postgres": "POSTGRES_BIND_ADDR",
    "ollama": "OLLAMA_BIND_ADDR",
    "neo4j": "NEO4J_BIND_ADDR",
    "minio": "MINIO_BIND_ADDR",
    "milvus": "MILVUS_BIND_ADDR",
    "redis": "REDIS_BIND_ADDR",
    "keycloak": "KEYCLOAK_BIND_ADDR",
}


def _bind_pattern(name: str) -> re.Pattern[str]:
    key = BIND_ADDRESS_KEYS.get(name)
    if key is None:
        return re.compile(r"^127\.0\.0\.1:")
    return re.compile(r"^\$\{" + re.escape(key) + r"(:-127\.0\.0\.1)?\}:")

_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):\s*$")
_SERVICE_KEY = re.compile(r"^  ([A-Za-z0-9][A-Za-z0-9_.-]*):\s*$")
_PORT_ENTRY = re.compile(r'^\s*-\s*"([^"]+)"\s*(?:#.*)?$')


def _service_blocks(path: Path) -> dict[str, list[str]]:
    """Map each top-level service name to its raw block of lines."""
    lines = path.read_text(encoding="utf-8").splitlines()
    in_services = False
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if _TOP_LEVEL_KEY.match(line):
            in_services = line.strip() == "services:"
            current = None
            continue
        if not in_services:
            continue
        match = _SERVICE_KEY.match(line)
        if match:
            current = match.group(1)
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(line)
    return blocks


class ComposeExposureTests(unittest.TestCase):
    def test_infrastructure_ports_are_loopback_only(self) -> None:
        blocks = _service_blocks(SERVICES)
        offenders = []
        for name, lines in blocks.items():
            if name in EXEMPT_SERVICES:
                continue
            required_prefix = _bind_pattern(name)
            in_ports = False
            for line in lines:
                if re.match(r"^\s{4}ports:\s*$", line):
                    in_ports = True
                    continue
                if in_ports:
                    port_match = _PORT_ENTRY.match(line)
                    if port_match is None:
                        in_ports = False
                        continue
                    mapping = port_match.group(1)
                    if not required_prefix.match(mapping):
                        offenders.append(f"{name}: {mapping}")
        self.assertEqual(offenders, [], f"published on all interfaces: {offenders}")

    def test_every_bind_address_key_is_used_by_its_service(self) -> None:
        """The policy table above and the compose file name the same services."""
        blocks = _service_blocks(SERVICES)
        for name, key in BIND_ADDRESS_KEYS.items():
            with self.subTest(service=name):
                self.assertIn(name, blocks)
                self.assertIn("${" + key, "\n".join(blocks[name]))

    def test_redis_requires_a_password(self) -> None:
        blocks = _service_blocks(SERVICES)
        redis_lines = "\n".join(blocks.get("redis", []))
        self.assertIn("--requirepass", redis_lines)

    def test_production_env_file_is_required(self) -> None:
        lines = PROD.read_text(encoding="utf-8").splitlines()
        offenders = []
        pending_path: str | None = None
        for line in lines:
            path_match = re.match(r"^\s*-\s*path:\s*(\S+)\s*$", line)
            if path_match:
                pending_path = path_match.group(1)
                continue
            required_match = re.match(r"^\s*required:\s*(true|false)\s*$", line)
            if required_match and pending_path is not None:
                if required_match.group(1) == "false":
                    offenders.append(pending_path)
                pending_path = None
        self.assertEqual(offenders, [], f"optional env_file in production: {offenders}")


if __name__ == "__main__":
    unittest.main()
