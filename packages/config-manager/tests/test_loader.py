"""Loader behavior tests run in isolated subprocesses."""

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def run_python(code: str, *, values: str = "", overrides: dict[str, str] | None = None) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "configs/.env"
        path.parent.mkdir()
        path.write_text(values)
        cwd = root / "apps/service"
        cwd.mkdir(parents=True)
        (cwd / ".env").write_text("LOCAL_ONLY=wrong\nPOSTGRES_HOST=wrong\n")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "AGENTICAI_ENV_FILE": str(path),
            "PYTHONPATH": str(SRC),
            **(overrides or {}),
        }
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stderr[-3000:]


def test_loads_once_preserves_process_values_and_ignores_local_file():
    run_python(
        """
        import os
        from config_manager import load_environment
        load_environment()
        assert os.environ['QUOTED'] == 'quoted value'
        assert os.environ['POSTGRES_HOST'] == 'injected'
        assert os.environ['EMPTY'] == ''
        assert 'LOCAL_ONLY' not in os.environ
        del os.environ['TOKEN']
        load_environment()
        assert 'TOKEN' not in os.environ
        from config_manager import env
        assert env.get('QUOTED') == 'quoted value'
        assert 'TOKEN' not in os.environ
        """,
        values='QUOTED="quoted value"\nPOSTGRES_HOST=file\nEMPTY=\nTOKEN=synthetic\n',
        overrides={"POSTGRES_HOST": "injected"},
    )


def test_default_path_is_independent_of_working_directory():
    run_python(
        """
        import os
        from pathlib import Path
        from config_manager import manager as env_manager
        env_manager.ROOT = Path(os.environ.pop('AGENTICAI_ENV_FILE')).parents[1]
        env_manager.load_environment()
        assert os.environ['CENTRAL_ONLY'] == 'loaded'
        assert 'LOCAL_ONLY' not in os.environ
        """,
        values="CENTRAL_ONLY=loaded\n",
    )


def test_explicit_missing_file_fails_but_default_missing_file_is_optional():
    run_python(
        """
        import os
        from pathlib import Path
        from config_manager import manager as env_manager
        path = Path(os.environ['AGENTICAI_ENV_FILE'])
        path.unlink()
        try:
            env_manager.load_environment()
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Explicit file must exist')
        del os.environ['AGENTICAI_ENV_FILE']
        env_manager.ROOT = path.parents[1]
        env_manager.load_environment()
        """,
    )


def test_internal_and_web_accessors_read_independent_keys():
    run_python(
        """
        import os
        from config_manager import env
        keys = (
            'INTERNAL_TOOLS_SERVICE_URL', 'INTERNAL_RAG_SERVICE_API_URL',
            'INTERNAL_USER_SERVICE_URL', 'INTERNAL_SERVICE_TOKEN',
            'INTERNAL_AGENT_SERVICE_URL',
            'USER_SERVICE_URL', 'AGENT_SERVICE_URL', 'RAG_SERVICE_URL',
            'AUTH_TYPE',
        )
        for key in keys:
            assert isinstance(getattr(type(env), key, None), property), key
            os.environ[key] = 'synthetic-' + key
        for key in keys:
            assert getattr(env, key) == 'synthetic-' + key
        for key in keys:
            del os.environ[key]
            assert getattr(env, key) is None
        """,
    )


def test_catalog_internal_urls_do_not_override_web_urls():
    run_python(
        """
        import os
        from pathlib import Path
        from config_manager import manager
        manager.ROOT = Path(os.environ['AGENTICAI_ENV_FILE']).parents[1]
        spec = manager.build_specs()['configs']
        defaults = {item.name: item.default for item in spec.variables}
        for key, suffix in {
            'MCP_INTERNAL_URL': '/internal/tools-service/mcp',
            'TOOLS_SERVICE_URL': '/tools-service/mcp',
            'INTERNAL_TOOLS_SERVICE_URL': '/internal/tools-service/mcp',
            'INTERNAL_RAG_SERVICE_API_URL': '/internal/rag-service',
            'INTERNAL_USER_SERVICE_URL': '/internal/user-service',
            'INTERNAL_AGENT_SERVICE_URL': '/internal/agent-service/api/v1',
            'USER_SERVICE_URL': '/user-service',
            'AGENT_SERVICE_URL': '/agent-service',
            'RAG_SERVICE_URL': '/rag-service',
        }.items():
            assert defaults.get(key) == 'http://localhost:8000' + suffix, key
        assert len(defaults) == len(spec.variables)
        assert 'RAG_API_URL' not in defaults
        assert 'RAG_SERVICE_API_URL' not in defaults
        assert '/internal/' not in defaults['TOOLS_SERVICE_URL']
        assert 'MCP_SERVER_URL' not in defaults
        manager.init_env_file(spec)
        values = manager.parse_env_file(spec.path)
        assert values['USER_SERVICE_URL'] == 'http://web-gateway/user-service'
        assert values['INTERNAL_USER_SERVICE_URL'] == 'http://private-gateway/user-service'
        assert manager.check_env_file(spec).ok
        """,
        values=(
            'USER_SERVICE_URL=http://web-gateway/user-service\n'
            'INTERNAL_USER_SERVICE_URL=http://private-gateway/user-service\n'
            'GATEWAY_ALLOWED_REDIRECT_URIS=["http://web-gateway/auth/oidc/callback"]\n'
        ),
    )
