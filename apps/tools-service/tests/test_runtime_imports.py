"""Exercise imports without pytest's additional source paths."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_modules_import_without_test_pythonpath():
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.core import api_versioning, schema; from src.tools import web_tools",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_unsupported_sandbox_fails_before_launch(monkeypatch, tmp_path):
    import pytest

    from src.core import sandbox

    monkeypatch.setattr(sandbox, "resource", None)
    with pytest.raises(RuntimeError, match="POSIX"):
        sandbox.run_capped([sys.executable, "-c", "pass"], cwd=tmp_path)


async def test_unsupported_async_sandbox_fails_before_launch(monkeypatch, tmp_path):
    import pytest

    from src.core import sandbox

    monkeypatch.setattr(sandbox, "resource", None)
    with pytest.raises(RuntimeError, match="POSIX"):
        await sandbox.run_sandboxed([sys.executable, "-c", "pass"], cwd=tmp_path, execution_timeout=1)
