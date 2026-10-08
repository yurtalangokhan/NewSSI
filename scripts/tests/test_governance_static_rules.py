"""The static governance rules, as assertions instead of a one-off report.

Each test restates one rule from the ED-CAGE static scan using that rule's own
evidence — the compose files it actually inspects, the regex groups it actually
matches, the OPA denials it actually emitted — so a regression fails here rather
than in the next quarterly scan.
"""

import re
import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

#: The compose files the scanner enumerates. Files outside this list (notably
#: deploy/docker/docker-compose-services.yml) are not evaluated by CMP-002.
COMPOSE_CANDIDATES = (
    "apps/rag-service/docker-compose.yml",
    "deploy/docker/docker-compose-dev.yml",
    "deploy/docker/docker-compose-prod.yml",
    "apps/agent-service/compose.yaml",
    "apps/user-service/compose.yaml",
)
#: Services the scanner skips: observability sidecars, not application services.
HEALTHCHECK_EXEMPT = {
    "grafana", "grafana-server", "prometheus", "prometheus-server",
    "tracing-server", "admin-server",
}

CONFIG_GLOBS = ("*.yaml", "*.yml", "*.properties", "*.conf", "*.json", "*.xml")
CONFIG_EXCLUDE = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "outputs", "dist", "build", "node_modules", ".tmp", ".next",
}


def _load(path: str) -> dict:
    return yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8")) or {}


def _config_files():
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file() or any(part in CONFIG_EXCLUDE for part in path.parts):
            continue
        if not any(path.match(glob) for glob in CONFIG_GLOBS):
            continue
        if path.stat().st_size > 1_048_576:
            continue
        yield path


def _matches_anywhere(patterns) -> str | None:
    for path in _config_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(re.search(p, line) for p in patterns):
                return f"{path.relative_to(REPOSITORY_ROOT)}:{number}"
    return None


class ComposeContractTests(unittest.TestCase):
    def test_cmp_002_every_application_service_declares_a_healthcheck(self) -> None:
        missing = []
        for candidate in COMPOSE_CANDIDATES:
            if not (REPOSITORY_ROOT / candidate).exists():
                continue
            for name, service in (_load(candidate).get("services") or {}).items():
                if name in HEALTHCHECK_EXEMPT or not isinstance(service, dict):
                    continue
                if "healthcheck" not in service:
                    missing.append(f"{candidate}::{name}")
        self.assertEqual([], missing, "CMP-002: services without a healthcheck")

    def test_cmp_003_no_service_asks_for_host_level_isolation(self) -> None:
        offenders = []
        for candidate in (*COMPOSE_CANDIDATES, "deploy/docker/docker-compose-services.yml"):
            if not (REPOSITORY_ROOT / candidate).exists():
                continue
            for name, service in (_load(candidate).get("services") or {}).items():
                if not isinstance(service, dict):
                    continue
                if service.get("privileged"):
                    offenders.append(f"{candidate}::{name} privileged")
                for key in ("network_mode", "pid", "ipc"):
                    if str(service.get(key, "")).startswith("host"):
                        offenders.append(f"{candidate}::{name} {key}=host")
        self.assertEqual([], offenders, "CMP-003: host-level isolation requested")

    def test_web_waits_for_its_dependencies_to_report_healthy(self) -> None:
        """A started container is not a ready one; the web app calls these on render."""
        for compose in ("deploy/docker/docker-compose-dev.yml", "deploy/docker/docker-compose-prod.yml"):
            depends = (_load(compose)["services"]["web"].get("depends_on")) or {}
            self.assertIsInstance(depends, dict, f"{compose}: web depends_on lost its conditions")
            for service, spec in depends.items():
                self.assertEqual(
                    "service_healthy", spec.get("condition"),
                    f"{compose}: web waits on {service} without a health condition",
                )


class ResiliencePolicyTests(unittest.TestCase):
    def test_rel_004_circuit_breaker_policy_is_configured(self) -> None:
        self.assertIsNotNone(
            _matches_anywhere([r"(?i)circuitbreaker", r"(?i)resilience4j\.circuitbreaker"]),
            "REL-004: no circuit breaker configuration found",
        )

    def test_rel_005_retry_attempts_are_bounded(self) -> None:
        self.assertIsNotNone(
            _matches_anywhere([r"(?i)maxAttempts", r"(?i)maxRetryAttempts", r"(?i)maximumAttempts"]),
            "REL-005: no bounded retry configuration found",
        )

    def test_the_policy_file_is_the_one_the_code_reads(self) -> None:
        policy = _load("configs/resilience.yaml")
        defaults = policy["defaults"]
        self.assertIn("timeoutSeconds", defaults)
        self.assertIn("maxAttempts", defaults["retry"])
        self.assertLessEqual(
            {"initialSeconds", "multiplier", "maxSeconds"}, set(defaults["retry"]["backoff"])
        )
        self.assertLessEqual(
            {"failureThreshold", "resetTimeoutSeconds"}, set(defaults["circuitBreaker"])
        )


class ArchitectureCatalogTests(unittest.TestCase):
    """TOOL-OPA-001: the two denials the OPA baseline emitted."""

    def setUp(self) -> None:
        self.catalog = _load("docs/architecture/service-catalog.yaml")

    def test_at_least_one_critical_service_is_declared(self) -> None:
        self.assertTrue(self.catalog.get("critical_services"))

    def test_every_service_has_an_owner(self) -> None:
        unowned = [s.get("name") for s in self.catalog.get("services", []) if not s.get("owner")]
        self.assertEqual([], unowned, "services without an owner")


class GatewayExposureTests(unittest.TestCase):
    def test_metrics_are_not_reachable_through_the_gateway(self) -> None:
        """Metrics are scraped on the pod network, never published at the edge."""
        apisix = _load("configs/apisix/apisix.yaml")
        terminated = {
            path for route in apisix["routes"]
            if route.get("plugins", {}).get("fault-injection", {}).get("abort", {}).get("http_status") == 404
            for path in route.get("uris", [])
        }
        for service in ("user-service", "rag-service", "tools-service", "agent-service"):
            for prefix in (f"/internal/{service}", f"/{service}"):
                self.assertIn(f"{prefix}/metrics", terminated)


if __name__ == "__main__":
    unittest.main()
