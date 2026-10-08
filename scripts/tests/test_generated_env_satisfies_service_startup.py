"""A generated .env must contain everything the service refuses to start without.

env_manager.py writes each service's .env; each service declares the
variables it hard-requires at startup (REQUIRED_ENV_NAMES, checked by
require_env, which raises). Those two lists are maintained in different
files by different people, and nothing tied them together: dropping a
variable from the generator left a service that generates its own
configuration and then refuses to boot on it.

That is exactly what happened to tools-service -- POSTGRES_* was removed
from the generator while settings.py still required it -- so this asserts
the relationship rather than either list's contents.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _generated_variables(service: str) -> set[str]:
    """The variable names env_manager writes into one service's .env."""
    source = (ROOT / "packages" / "config_manager" / "src" / "config_manager" / "manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not isinstance(key, ast.Constant) or key.value != service:
                continue
            names: set[str] = set()
            for call in ast.walk(value):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "var"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                ):
                    names.add(call.args[0].value)
            if names:
                return {_flattened_name(service, name) for name in names}
    raise AssertionError(f"no env spec found for {service!r}")


def _flattened_name(service: str, name: str) -> str:
    """The name a spec variable ends up with in the central configs/.env.

    The specs still declare the generic ``POSTGRES_*``/``KEYCLOAK_*`` names;
    manager.py rewrites them to the per-service ones when it flattens every
    spec into the single central file. Mirrors that pass so this test compares
    the names a service actually receives.
    """
    prefix = service.removesuffix("-service").upper().replace("TOOLS", "TOOL")
    if service.endswith("-service"):
        if name in {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}:
            return name.replace("POSTGRES_", f"POSTGRES_{prefix}_SERVICE_")
        if name in {"KEYCLOAK_CLIENT_ID", "KEYCLOAK_CLIENT_SECRET", "KEYCLOAK_AUDIENCE"}:
            return name.replace("KEYCLOAK_", f"KEYCLOAK_{prefix}_SERVICE_")
    if service == "agent-service" and name == "PORT":
        return "AGENT_SERVICE_PORT"
    if service == "user-service" and name == "SERVICE_PORT":
        return "USER_SERVICE_PORT"
    return name


def _required_variables(service_dir: str, settings_path: str) -> set[str]:
    """The names a service refuses to start without."""
    source = (ROOT / "apps" / service_dir / settings_path).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "REQUIRED_ENV_NAMES" for t in node.targets
        ):
            return {
                element.value
                for element in ast.walk(node.value)
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    raise AssertionError(f"no REQUIRED_ENV_NAMES in {service_dir}/{settings_path}")


class GeneratedEnvCoversStartupRequirements(unittest.TestCase):
    def test_tools_service(self) -> None:
        generated = _generated_variables("tools-service")
        required = _required_variables("tools-service", "src/core/settings.py")

        missing = sorted(required - generated)
        self.assertEqual(
            missing,
            [],
            "tools-service requires these at startup but env_manager.py does not "
            f"generate them, so a freshly generated .env cannot boot it: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
