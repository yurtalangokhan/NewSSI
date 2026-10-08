"""Exercise configuration loading using synthetic files and isolated processes."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CentralEnvTests(unittest.TestCase):
    def run_python(self, code, *, service=None, values="", overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "configs/.env"
            path.parent.mkdir()
            path.write_text(values)
            cwd = root / "apps/service"
            cwd.mkdir(parents=True)
            (cwd / ".env").write_text("LOCAL_ONLY=wrong\nPOSTGRES_HOST=wrong\n")
            python_path = "Scripts/python.exe" if os.name == "nt" else "bin/python"
            interpreter = ROOT / f"apps/{service}/.venv/{python_path}" if service else sys.executable
            environment = {
                "PATH": os.environ.get("PATH", ""),
                **({"SystemRoot": os.environ["SystemRoot"]} if os.name == "nt" else {}),
                "AGENTICAI_ENV_FILE": str(path),
                "PYTHONPATH": ""
                if service
                else os.pathsep.join([str(ROOT), str(ROOT / "packages/config-manager/src")]),
                **(overrides or {}),
            }
            result = subprocess.run(
                [str(interpreter), "-c", textwrap.dedent(code)],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_each_service_uses_central_database_auth_and_port_keys(self):
        values = (
            "\n".join(
                [
                    "POSTGRES_HOST=central-host",
                    "POSTGRES_PORT=6543",
                    "IS_TESTING=true",
                    "NEO4J_PASSWORD=synthetic-neo4j",
                    "INTERNAL_USER_SERVICE_URL=http://gateway/internal/user",
                    "USER_SERVICE_URL=http://gateway/public/user",
                    "INTERNAL_SERVICE_TOKEN=synthetic-internal",
                    "KEYCLOAK_CLIENT_ID=web-login",
                    "MCP_HOST=127.0.0.1",
                    "AGENT_SERVICE_PORT=9101",
                    "USER_SERVICE_PORT=9102",
                    "TOOLS_SERVICE_PORT=9103",
                    "AUTHENTICATION_SECRET=synthetic-auth",
                    "USER_API_KEY_ENCRYPTION_KEY=synthetic-api-key-key",
                    "SYSTEM_SETTINGS_ENCRYPTION_KEY=synthetic-settings-key",
                    "EXTERNAL_KEYCLOAK_CLIENT_SECRET=external-only",
                    *[
                        f"POSTGRES_{name}_SERVICE_{key}={name.lower()}_{key.lower()}"
                        for name in ("AGENT", "USER", "RAG", "TOOL")
                        for key in ("USER", "PASSWORD", "DB")
                    ],
                    *[
                        f"KEYCLOAK_{name}_SERVICE_{key}={name.lower()}_{key.lower()}"
                        for name in ("AGENT", "USER", "RAG", "TOOL")
                        for key in ("CLIENT_ID", "CLIENT_SECRET", "AUDIENCE")
                    ],
                ]
            )
            + "\n"
        )
        cases = {
            "agent-service": """
                assert env.AGENT_SERVICE_PORT == 9101
                assert env.POSTGRES_AGENT_SERVICE_DB == 'agent_db'
                assert env.AUTHENTICATION_SECRET == 'synthetic-auth'
                assert env.KEYCLOAK_AGENT_SERVICE_AUDIENCE == 'agent_audience'
            """,
            "user-service": """
                assert env.USER_SERVICE_PORT == 9102
                assert env.POSTGRES_USER_SERVICE_DB == 'user_db'
                assert '/user_db' in env.database_url
                assert env.USER_API_KEY_ENCRYPTION_KEY == 'synthetic-api-key-key'
                assert env.SYSTEM_SETTINGS_ENCRYPTION_KEY == 'synthetic-settings-key'
                assert env.KEYCLOAK_USER_SERVICE_CLIENT_SECRET == 'user_client_secret'
                assert env.EXTERNAL_KEYCLOAK_CLIENT_SECRET == 'external-only'
            """,
            "rag-service": """
                assert env.POSTGRES_RAG_SERVICE_DB == 'rag_db'
                assert env.KEYCLOAK_CLIENT_ID == 'web-login'
                assert env.POSTGRES_HOST == 'central-host'
                assert env.INTERNAL_USER_SERVICE_URL == 'http://gateway/internal/user'
            """,
            "tools-service": """
                assert env.tool_postgres_config['database'] == 'tool_db'
                assert env.TOOLS_SERVICE_PORT == 9103
                assert env.INTERNAL_USER_SERVICE_URL == 'http://gateway/internal/user'
                assert os.environ['POSTGRES_TOOL_SERVICE_PASSWORD'] == 'tool_password'
            """,
        }
        for service, assertions in cases.items():
            with self.subTest(service=service):
                code = (
                    "import os\nfrom config_manager import env\n"
                    + textwrap.dedent(assertions)
                    + "\nassert 'LOCAL_ONLY' not in os.environ\n"
                )
                self.run_python(code, service=service, values=values)

    def test_cli_only_initializes_the_central_file_and_preserves_existing_values(self):
        self.run_python(
            """
            import os
            from pathlib import Path
            from config_manager import manager as env_manager
            path = Path(os.environ['AGENTICAI_ENV_FILE'])
            env_manager.ROOT = path.parents[1]
            specs = env_manager.selected_specs(['agent-service', 'tools-service'])
            assert len(specs) == 1 and specs[0].path == path
            env_manager.init_env_file(specs[0])
            values = env_manager.parse_env_file(path)
            assert values['POSTGRES_USER_SERVICE_DB'] == 'operator_db'
            for service in ['AGENT', 'USER', 'RAG', 'TOOL']:
                assert f'POSTGRES_{service}_SERVICE_DB' in values
            assert 'AUTHENTICATION_SECRET' in values
            assert 'LLM_PROVIDER_API_ENCRYPTION_KEY' in values
            assert 'KONG_DATABASE' not in values
            assert not (env_manager.ROOT / 'apps/agent-service').exists()
            """,
            values="POSTGRES_USER_SERVICE_DB=operator_db\n",
        )

    def test_backend_compose_paths_resolve_to_the_central_file_and_repository(self):
        import yaml

        for mode in ("dev", "prod"):
            path = ROOT / f"deploy/docker/docker-compose-{mode}.yml"
            compose = yaml.safe_load(path.read_text())
            for service in ("agent-service", "user-service", "rag-service", "tools-service"):
                with self.subTest(mode=mode, service=service):
                    definition = compose["services"][service]
                    env_file = definition["env_file"][0]
                    env_file = env_file["path"] if isinstance(env_file, dict) else env_file
                    self.assertEqual((path.parent / env_file).resolve(), ROOT / "configs/.env")
                    self.assertEqual((path.parent / definition["build"]["context"]).resolve(), ROOT)


if __name__ == "__main__":
    unittest.main()
