import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"


def launch(tmp_path, code, *, overrides=None, exists=True):
    file = tmp_path / "central.env"
    if exists:
        file.write_text("GATEWAY_URL=http://central.example:8000\nLITERAL_VALUE=price$5\n")
    environment = dict(os.environ)
    environment.pop("GATEWAY_URL", None)
    environment.update(PYTHONPATH=str(SOURCE), AGENTICAI_ENV_FILE=str(file))
    environment.update(overrides or {})
    return subprocess.run(
        [sys.executable, "-m", "config_manager.run", "--", sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_loads_central_environment_without_interpolation(tmp_path):
    result = launch(
        tmp_path,
        "import os; assert os.environ['GATEWAY_URL'] == 'http://central.example:8000'; "
        "assert os.environ['LITERAL_VALUE'] == 'price$5'",
    )
    assert result.returncode == 0, result.stderr


def test_preserves_process_overrides_and_child_exit_status(tmp_path):
    result = launch(
        tmp_path,
        "import os,sys; assert os.environ['GATEWAY_URL'] == 'http://override.example'; sys.exit(7)",
        overrides={"GATEWAY_URL": "http://override.example"},
    )
    assert result.returncode == 7, result.stderr


def test_missing_explicit_file_prevents_launch(tmp_path):
    result = launch(tmp_path, "print('CHILD_STARTED')", exists=False)
    assert result.returncode != 0
    assert "Central environment file does not exist" in result.stderr
    assert "CHILD_STARTED" not in result.stdout
