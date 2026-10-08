"""Bounded subprocess execution. Spec TS-1.

execute_shell used shell=True with a five-substring blocklist
(["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]) as its only defence,
which "rm  -rf /" (double space), "rm -rf /*", or a base64-encoded command
all defeat trivially. run_sandboxed replaces free-form shell execution
with argv-only exec, its own process group so a timeout kills grandchildren,
resource limits, and a hard output cap.
"""

import asyncio
from pathlib import Path

import pytest

from src.core.sandbox import MAX_OUTPUT_BYTES, run_sandboxed


@pytest.mark.asyncio
async def test_captures_stdout_and_exit_code(tmp_path: Path):
    result = await run_sandboxed(["echo", "hello"], cwd=tmp_path, execution_timeout=5)
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_nonzero_exit_code_is_reported(tmp_path: Path):
    result = await run_sandboxed(
        ["python3", "-c", "import sys; sys.exit(3)"], cwd=tmp_path, execution_timeout=5
    )
    assert result.exit_code == 3


@pytest.mark.asyncio
async def test_argv_is_never_interpreted_by_a_shell(tmp_path: Path):
    """A value that would be shell metacharacters if this were shell=True
    must be passed through to the program as a literal argument."""
    marker = tmp_path / "pwned"
    result = await run_sandboxed(["echo", f"x; touch {marker}"], cwd=tmp_path, execution_timeout=5)
    assert marker.exists() is False
    assert "touch" in result.stdout  # printed literally, not executed


@pytest.mark.asyncio
async def test_output_is_capped(tmp_path: Path):
    result = await run_sandboxed(
        ["python3", "-c", f"print('x' * {MAX_OUTPUT_BYTES * 2})"],
        cwd=tmp_path,
        execution_timeout=30,
    )
    assert len(result.stdout.encode("utf-8")) <= MAX_OUTPUT_BYTES + 200
    assert result.truncated is True


@pytest.mark.asyncio
async def test_timeout_is_reported(tmp_path: Path):
    result = await run_sandboxed(
        ["python3", "-c", "import time; time.sleep(30)"], cwd=tmp_path, execution_timeout=1
    )
    assert result.timed_out is True


@pytest.mark.asyncio
async def test_timeout_kills_orphaned_grandchildren(tmp_path: Path):
    marker = tmp_path / "late"
    script = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',"
        f"\"import time;time.sleep(6);open(r'{marker}','w').write('x')\"]);"
        "time.sleep(30)"
    )
    result = await run_sandboxed(["python3", "-c", script], cwd=tmp_path, execution_timeout=2)
    assert result.timed_out is True
    await asyncio.sleep(7)
    assert marker.exists() is False, "grandchild survived the timeout"


@pytest.mark.asyncio
async def test_memory_limit_terminates_runaway_allocation(tmp_path: Path):
    result = await run_sandboxed(
        ["python3", "-c", "x = bytearray(4 * 1024 * 1024 * 1024)"],
        cwd=tmp_path,
        execution_timeout=30,
    )
    assert result.exit_code != 0


@pytest.mark.asyncio
async def test_requested_timeout_above_max_is_clamped(tmp_path: Path, monkeypatch):
    # Patch the cap itself down to a couple of seconds rather than waiting
    # out the real MAX_TIMEOUT_SECONDS (120s), which would make this one
    # test dominate the whole suite's runtime.
    import time as time_module

    from src.core import sandbox as sandbox_module

    monkeypatch.setattr(sandbox_module, "MAX_TIMEOUT_SECONDS", 2.0)

    started = time_module.monotonic()
    result = await run_sandboxed(
        ["python3", "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        execution_timeout=9999,
    )
    elapsed = time_module.monotonic() - started
    assert result.timed_out is True
    assert elapsed < 10


@pytest.mark.asyncio
async def test_empty_argv_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        await run_sandboxed([], cwd=tmp_path, execution_timeout=5)


@pytest.mark.asyncio
async def test_process_runs_with_a_minimal_clean_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "must-not-leak")
    result = await run_sandboxed(
        ["python3", "-c", "import os; print(os.environ.get('SUPER_SECRET_TOKEN', 'ABSENT'))"],
        cwd=tmp_path,
        execution_timeout=5,
    )
    assert "ABSENT" in result.stdout
    assert "must-not-leak" not in result.stdout
