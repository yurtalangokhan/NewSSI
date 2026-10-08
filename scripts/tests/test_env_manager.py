import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config_manager import manager as env_manager
from config_manager.manager import (
    EnvFileSpec,
    EnvVarSpec,
    build_specs,
    check_env_file,
    init_env_file,
)

_test_root = None
_root_patch = None
_environment_patch = None


def setUpModule():
    global _test_root, _root_patch, _environment_patch
    _test_root = tempfile.TemporaryDirectory()
    _root_patch = mock.patch.object(env_manager, "ROOT", Path(_test_root.name))
    _root_patch.start()
    # The central accessor loads configs/.env at import time. Generated-default
    # tests must not inherit a developer's configured credentials.
    _environment_patch = mock.patch.dict(os.environ, {}, clear=True)
    _environment_patch.start()
    env_manager._shared_secret_cache.clear()


def tearDownModule():
    _environment_patch.stop()
    _root_patch.stop()
    _test_root.cleanup()
    env_manager._shared_secret_cache.clear()


class EnvManagerTests(unittest.TestCase):
    def test_generated_keycloak_clients_target_v1_realm(self) -> None:
        variables = {
            item.name: item.default
            for item in build_specs()["configs"].variables
        }
        self.assertEqual(variables["KEYCLOAK_REALM"], "agenticai-v1")
        self.assertTrue(variables["KEYCLOAK_ISSUER_URL"].endswith("/realms/agenticai-v1"))
        self.assertEqual(variables["KEYCLOAK_CLIENT_ID"], "web-client")
        self.assertEqual(variables["KEYCLOAK_LOGIN_CLIENT_ID"], "web-client")
        self.assertEqual(variables["KEYCLOAK_USER_SERVICE_CLIENT_ID"], "user-service-client")
        self.assertEqual(variables["KEYCLOAK_USER_SERVICE_AUDIENCE"], "user-service-client")
        self.assertEqual(variables["KEYCLOAK_AGENT_SERVICE_AUDIENCE"], "agent-service-client")
        self.assertEqual(variables["KEYCLOAK_AGENT_SERVICE_CLIENT_ID"], "agent-service-client")
        self.assertEqual(variables["KEYCLOAK_RAG_SERVICE_CLIENT_ID"], "rag-service-client")
        self.assertEqual(variables["KEYCLOAK_TOOLS_SERVICE_CLIENT_ID"], "tools-service-client")

    def test_keycloak_realm_and_service_ids_are_required(self) -> None:
        from config_manager.accessor import ConfigManager

        settings = ConfigManager()
        for key in (
            "KEYCLOAK_REALM",
            "KEYCLOAK_USER_SERVICE_CLIENT_ID",
            "KEYCLOAK_LOGIN_CLIENT_ID",
            "KEYCLOAK_CLIENT_ID",
            "KEYCLOAK_AGENT_SERVICE_CLIENT_ID",
            "KEYCLOAK_RAG_SERVICE_CLIENT_ID",
            "KEYCLOAK_TOOLS_SERVICE_CLIENT_ID",
        ):
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: ""}):
                with self.assertRaisesRegex(ValueError, key):
                    getattr(settings, key)

    def test_web_has_four_explicit_service_roots(self) -> None:
        """The web section of the catalog names the gateway roots the web schema
        requires (`apps/web/src/lib/env/schema.ts`) and none of the keys its code
        no longer reads (`apps/web/src/lib/api/serviceConfiguration.test.ts`)."""
        variables = {
            item.name: item.default
            for item in env_manager._build_sections()["web"].variables
        }
        for obsolete in ("INTERNAL_URL", "LANGCONNECT_URL", "MCP_SERVER_URL"):
            self.assertNotIn(obsolete, variables)
        # Gateway paths of apps/web/docs/runbook.md: the MCP server of tools-service
        # is mounted at /tools-service/mcp, its internal twin at /internal/tools-service/mcp.
        for key, mount in (
            ("AGENT_SERVICE_URL", "agent-service"),
            ("RAG_SERVICE_URL", "rag-service"),
            ("USER_SERVICE_URL", "user-service"),
            ("TOOLS_SERVICE_URL", "tools-service/mcp"),
            ("MCP_INTERNAL_URL", "internal/tools-service/mcp"),
        ):
            self.assertEqual(variables[key], f"http://localhost:8000/{mount}")

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


class ForbiddenValueTests(unittest.TestCase):
    def test_check_env_file_reports_a_known_weak_value_even_if_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("SECRET_KEY=minioadmin\n", encoding="utf-8")

            spec = EnvFileSpec(
                path=env_path,
                title="test",
                variables=(EnvVarSpec("SECRET_KEY", "a secret"),),
            )

            result = check_env_file(spec)

        self.assertEqual(result.forbidden, ("SECRET_KEY",))
        self.assertFalse(result.ok)

    def test_not_secret_var_is_exempt_from_the_forbidden_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("USERNAME_KEY=minioadmin\n", encoding="utf-8")

            spec = EnvFileSpec(
                path=env_path,
                title="test",
                variables=(EnvVarSpec("USERNAME_KEY", "a username", not_secret=True),),
            )

            result = check_env_file(spec)

        self.assertEqual(result.forbidden, ())
        self.assertTrue(result.ok)


class GenerateValueTests(unittest.TestCase):
    def test_token_generation_is_nonempty_and_url_safe(self) -> None:
        value = env_manager.generate_value("token")
        self.assertTrue(value)
        self.assertNotIn(" ", value)

    def test_fernet_generation_produces_a_usable_fernet_key(self) -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            self.skipTest("cryptography not installed in this interpreter")

        value = env_manager.generate_value("fernet")
        Fernet(value.encode("ascii"))  # raises if not a valid key

    def test_fernet_generation_falls_back_to_a_token_without_cryptography(self) -> None:
        with mock.patch.dict("sys.modules", {"cryptography.fernet": None}):
            value = env_manager.generate_fernet_key()
        self.assertTrue(value)
        self.assertNotIn(" ", value)

    def test_unset_kind_returns_empty_string(self) -> None:
        self.assertEqual(env_manager.generate_value(None), "")

    def test_init_env_file_uses_generate_when_there_is_no_literal_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            spec = EnvFileSpec(
                path=env_path,
                title="test",
                variables=(EnvVarSpec("A_TOKEN", "generated value", generate="token"),),
            )

            init_env_file(spec)
            content = env_manager.parse_env_file(env_path)

        self.assertNotEqual(content["A_TOKEN"], "")
        self.assertNotIn(content["A_TOKEN"], env_manager.FORBIDDEN_VALUES)


class SharedSecretTests(unittest.TestCase):
    def setUp(self) -> None:
        env_manager._shared_secret_cache.clear()

    def tearDown(self) -> None:
        env_manager._shared_secret_cache.clear()

    def test_process_environment_takes_precedence(self) -> None:
        with mock.patch.dict(os.environ, {"SOME_SHARED_SECRET": "pinned-by-operator"}):
            self.assertEqual(env_manager.shared_secret("SOME_SHARED_SECRET"), "pinned-by-operator")

    def test_reuses_a_value_already_written_to_a_managed_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir()
            (root / "configs/.env").write_text("SOME_SHARED_SECRET=already-set\n", encoding="utf-8")

            with (
                mock.patch.object(env_manager, "ROOT", root),
                mock.patch.object(env_manager, "ENV_FILES", ("configs/.env",)),
            ):
                self.assertEqual(env_manager.shared_secret("SOME_SHARED_SECRET"), "already-set")

    def test_a_forbidden_existing_value_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir()
            (root / "configs/.env").write_text("SOME_SHARED_SECRET=minioadmin\n", encoding="utf-8")

            with (
                mock.patch.object(env_manager, "ROOT", root),
                mock.patch.object(env_manager, "ENV_FILES", ("configs/.env",)),
            ):
                value = env_manager.shared_secret("SOME_SHARED_SECRET")

        self.assertNotEqual(value, "minioadmin")
        self.assertTrue(value)

    def test_generated_value_is_memoised_for_the_rest_of_the_run(self) -> None:
        first = env_manager.shared_secret("SOME_SHARED_SECRET")
        second = env_manager.shared_secret("SOME_SHARED_SECRET")
        self.assertEqual(first, second)


class BuildSpecsRegressionTests(unittest.TestCase):
    """Guards Task 14's fix: no service should ship a known-weak credential
    default any more. Keycloak bootstrap credentials are excluded -- see
    the comment on FORBIDDEN_VALUES -- since that hardening is out of
    scope for this pass.
    """

    def test_no_known_weak_credential_default_outside_keycloak_scope(self) -> None:
        specs = build_specs()
        offenders = [
            f"{spec_name}.{variable.name}"
            for spec_name, spec in specs.items()
            for variable in spec.variables
            if not variable.not_secret
            and variable.default in env_manager.FORBIDDEN_VALUES
            and not variable.name.startswith("KEYCLOAK_")
        ]
        self.assertEqual(offenders, [])

    def test_minio_access_credentials_match_minio_root_credentials(self) -> None:
        specs = build_specs()
        by_name = {
            variable.name: variable.default
            for spec in specs.values()
            for variable in spec.variables
            if variable.name
            in {"MINIO_ROOT_USER", "MINIO_ACCESS_KEY", "MINIO_ROOT_PASSWORD", "MINIO_SECRET_KEY"}
        }
        self.assertEqual(by_name["MINIO_ROOT_USER"], by_name["MINIO_ACCESS_KEY"])
        self.assertEqual(by_name["MINIO_ROOT_PASSWORD"], by_name["MINIO_SECRET_KEY"])

    def test_shared_credentials_are_identical_across_every_env_file(self) -> None:
        specs = build_specs()
        for key in (
            "POSTGRES_ADMIN_PASSWORD",
            "NEO4J_PASSWORD",
            "INTERNAL_SERVICE_TOKEN",
            "AUTHENTICATION_SECRET",
            "LLM_PROVIDER_API_ENCRYPTION_KEY",
            "REDIS_PASSWORD",
        ):
            values = {
                variable.default
                for spec in specs.values()
                for variable in spec.variables
                if variable.name == key
            }
            self.assertEqual(len(values), 1, f"{key} defaults differ across env files: {values}")

    def test_bind_addr_keys_default_to_loopback(self) -> None:
        """One key per published infrastructure service (see
        scripts/tests/test_compose_exposure.py); a shared server widens them."""
        specs = build_specs()
        for key in (
            "POSTGRES_BIND_ADDR",
            "OLLAMA_BIND_ADDR",
            "NEO4J_BIND_ADDR",
            "MINIO_BIND_ADDR",
            "MILVUS_BIND_ADDR",
            "REDIS_BIND_ADDR",
            "KEYCLOAK_BIND_ADDR",
        ):
            with self.subTest(key=key):
                (variable,) = [
                    v for spec in specs.values() for v in spec.variables if v.name == key
                ]
                self.assertEqual(variable.default, "127.0.0.1")

    def test_generated_central_file_uses_the_loopback_milvus_default(self) -> None:
        spec = build_specs()["configs"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "configs/.env"
            init_env_file(EnvFileSpec(path, spec.title, spec.variables))
            self.assertEqual(env_manager.parse_env_file(path)["MILVUS_BIND_ADDR"], "127.0.0.1")

    def test_allow_origins_has_no_wildcard_default(self) -> None:
        """The central catalog may declare the key but must not default to a wildcard."""
        specs = build_specs()
        (variable,) = [
            v for spec in specs.values() for v in spec.variables if v.name == "ALLOW_ORIGINS"
        ]
        self.assertEqual(variable.default, "")
        self.assertFalse(variable.required)


if __name__ == "__main__":
    unittest.main()


class NoShippedCredentialsTests(unittest.TestCase):
    """`make env-init` must not write a credential that ships in the repo.

    A default password in a spec is the same defect as a default password in
    settings.py: every environment initialised from it shares one credential
    that is public to anyone with repository access. The service-side defaults
    were removed; the generator has to stop supplying them too.

    These tests run against a *fresh clone* — no env files, no pinned process
    environment — because that is when defaults are actually consulted. On a
    developer machine `shared_secret` deliberately reuses whatever is already in
    the env files, so asserting against live specs would only measure that
    machine.
    """

    KNOWN_SHIPPED_CREDENTIALS = (
        "neo4j123",
        "minioadmin",
        "admin123",
        "Admin123!",
        "Test123!",
        "h6Uw3BxKqubQ",
        "your-super-secret",
        "dev-internal-service-token",
        "change-me-in-production",
    )

    CREDENTIAL_NAME = (
        "PASSWORD",
        "SECRET",
        "TOKEN",
        "LLM_PROVIDER_API_ENCRYPTION_KEY",
        "ACCESS_KEY",
    )

    #: Matches CREDENTIAL_NAME by spelling but selects a mode, not a credential.
    NOT_A_CREDENTIAL: set[str] = set()

    def _fresh_specs(self):
        """build_specs() as it behaves on a clone with nothing configured yet."""
        import os
        import tempfile
        from pathlib import Path

        from config_manager import manager as env_manager

        original_root = env_manager.ROOT
        removed = {
            key: os.environ.pop(key)
            for key in list(os.environ)
            if any(marker in key for marker in self.CREDENTIAL_NAME)
        }
        try:
            env_manager.ROOT = Path(tempfile.mkdtemp())
            env_manager._shared_secret_cache.clear()
            return env_manager.build_specs()
        finally:
            env_manager.ROOT = original_root
            env_manager._shared_secret_cache.clear()
            os.environ.update(removed)

    def _credential_vars(self):
        for name, spec in self._fresh_specs().items():
            for item in spec.variables:
                if item.name in self.NOT_A_CREDENTIAL or item.not_secret:
                    continue
                if any(marker in item.name for marker in self.CREDENTIAL_NAME):
                    yield name, item

    def test_no_spec_ships_a_known_credential(self) -> None:
        for spec_name, item in self._credential_vars():
            for marker in self.KNOWN_SHIPPED_CREDENTIALS:
                self.assertNotIn(
                    marker,
                    item.default,
                    f"{spec_name}:{item.name} ships the credential {marker!r}",
                )

    def test_generated_credentials_are_long_enough_to_be_secrets(self) -> None:
        for spec_name, item in self._credential_vars():
            if item.allow_empty or not item.default:
                continue
            with self.subTest(spec=spec_name, var=item.name):
                self.assertGreaterEqual(
                    len(item.default),
                    32,
                    f"{item.name} default is {item.default!r}, too short to be generated",
                )

    def test_shared_credentials_match_across_the_files_that_use_them(self) -> None:
        """Neo4j and MinIO are configured in one file and consumed in others."""
        specs = self._fresh_specs()

        def value(spec_name: str, var_name: str) -> str:
            return next(
                item.default for item in specs["configs"].variables if item.name == var_name
            )

        self.assertEqual(
            value("configs", "NEO4J_PASSWORD"), value("agent-service", "NEO4J_PASSWORD")
        )
        self.assertEqual(value("configs", "NEO4J_PASSWORD"), value("rag-service", "NEO4J_PASSWORD"))
        self.assertEqual(
            value("configs", "MINIO_ROOT_PASSWORD"), value("agent-service", "MINIO_SECRET_KEY")
        )

    def test_generated_secrets_differ_between_initialisations(self) -> None:
        spec_vars = (
            EnvVarSpec("LLM_PROVIDER_API_ENCRYPTION_KEY", "fernet", generate="fernet"),
            EnvVarSpec("SOME_TOKEN", "token", generate="token"),
        )
        written = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / ".env"
                init_env_file(EnvFileSpec(path=path, title="t", variables=spec_vars))
                written.append(path.read_text(encoding="utf-8"))

        self.assertNotEqual(written[0], written[1], "generated secrets must not repeat")
        for text in written:
            for line in text.splitlines():
                if "=" in line and not line.startswith("#"):
                    self.assertTrue(line.split("=", 1)[1], f"{line} was generated empty")


class GatewaySpecTests(unittest.TestCase):
    def test_gateway_container_redis_host_is_initialized_without_replacing_host(self) -> None:
        variables = tuple(
            item for item in build_specs()["configs"].variables
            if item.name in ("REDIS_HOST", "REDIS_HOST_CONTAINER")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("REDIS_HOST=custom-host\n")
            init_env_file(EnvFileSpec(path, "Redis hosts", variables))
            values = env_manager.parse_env_file(path)
            self.assertEqual(values["REDIS_HOST"], "custom-host")
            self.assertEqual(values["REDIS_HOST_CONTAINER"], "redis")

    def test_active_gateway_catalog_uses_apisix_address_contracts(self) -> None:
        variables = {item.name: item for item in build_specs()["configs"].variables}
        self.assertEqual(variables["APISIX_HTTP_PORT"].default, "8000")
        self.assertIn("APISIX_IMAGE_TAG", variables)
        self.assertEqual(variables["GATEWAY_URL"].default, "http://localhost:8000")
        self.assertFalse(any(name.startswith("KONG_") for name in variables))
        for service in ("USER", "AGENT", "RAG", "TOOLS"):
            name = f"{service}_SERVICE_UPSTREAM_ADDR"
            self.assertNotIn("://", variables[name].default)
            self.assertNotIn(f"{service}_SERVICE_UPSTREAM_URL", variables)
        self.assertEqual(
            variables["INTERNAL_USER_SERVICE_URL"].default,
            "http://localhost:8000/internal/user-service",
        )
        self.assertEqual(
            variables["USER_SERVICE_URL"].default,
            "http://localhost:8000/user-service",
        )

    def test_gateway_init_generates_secret_but_requires_explicit_redirects(self) -> None:
        variables = tuple(
            item for item in build_specs()["configs"].variables
            if item.name.startswith(("GATEWAY_", "APISIX_"))
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            spec = EnvFileSpec(path, "Synthetic Gateway settings", variables)
            init_env_file(spec)
            values = env_manager.parse_env_file(path)
            self.assertEqual(values["GATEWAY_KEYCLOAK_CLIENT_ID"], "gateway-client")
            self.assertGreaterEqual(len(values["GATEWAY_KEYCLOAK_CLIENT_SECRET"]), 32)
            self.assertEqual(values["GATEWAY_COOKIE_SECURE"], "true")
            self.assertEqual(check_env_file(spec).empty, ("GATEWAY_ALLOWED_REDIRECT_URIS",))
            first_secret = values["GATEWAY_KEYCLOAK_CLIENT_SECRET"]
            path.write_text(path.read_text().replace(
                "GATEWAY_ALLOWED_REDIRECT_URIS=\n",
                'GATEWAY_ALLOWED_REDIRECT_URIS=["https://app.example/auth/oidc/callback"]\n',
            ))
            init_env_file(spec)
            self.assertEqual(env_manager.parse_env_file(path)["GATEWAY_KEYCLOAK_CLIENT_SECRET"], first_secret)
            self.assertTrue(check_env_file(spec).ok)
