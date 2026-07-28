import tempfile
import unittest
from pathlib import Path

from scripts.env_manager import (
    EnvFileSpec,
    EnvVarSpec,
    build_specs,
    check_env_file,
    init_env_file,
)


class EnvManagerTests(unittest.TestCase):
    def test_check_env_file_reports_missing_and_extra_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("REQUIRED_KEY=value\nEXTRA_KEY=value\n", encoding="utf-8")

            spec = EnvFileSpec(
                path=env_path,
                title="test",
                variables=(
                    EnvVarSpec("REQUIRED_KEY", "required value"),
                    EnvVarSpec("MISSING_KEY", "missing value", default="fallback"),
                ),
            )

            result = check_env_file(spec)

        self.assertEqual(result.missing, ("MISSING_KEY",))
        self.assertEqual(result.extra, ("EXTRA_KEY",))

    def test_init_env_file_adds_missing_keys_without_rewriting_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("REQUIRED_KEY=custom\n", encoding="utf-8")

            spec = EnvFileSpec(
                path=env_path,
                title="test",
                variables=(
                    EnvVarSpec("REQUIRED_KEY", "required value", default="default"),
                    EnvVarSpec("MISSING_KEY", "missing value", default="fallback"),
                ),
            )

            init_env_file(spec)
            content = env_path.read_text(encoding="utf-8")

        self.assertIn("REQUIRED_KEY=custom\n", content)
        self.assertIn("# missing value\nMISSING_KEY=fallback\n", content)

    def test_generated_web_callback_defaults_use_localhost(self) -> None:
        specs = build_specs()
        watched_keys = {
            "WEB_DOMAIN",
            "KEYCLOAK_REDIRECT_URI",
            "KEYCLOAK_REDIRECT_URIS",
            "KEYCLOAK_WEB_ORIGIN",
            "KEYCLOAK_WEB_ORIGINS",
            "CORS_ALLOWED_ORIGINS",
        }

        defaults = [
            variable.default
            for spec in specs.values()
            for variable in spec.variables
            if variable.name in watched_keys
        ]

        self.assertTrue(defaults)
        for default in defaults:
            self.assertNotIn("10.101.90.13:3000", default)


if __name__ == "__main__":
    unittest.main()
