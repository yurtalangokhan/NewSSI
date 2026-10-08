"""The synchronous tools must get the same bounds as the sandboxed ones.

java_tools and git_tools call `subprocess.run` directly: no resource limits,
no output ceiling, and a timeout that only kills the direct child — so a
compiled program that forks, allocates, or prints without end was bounded by
nothing the service controls. `run_capped` is the drop-in that applies the
same limits `run_sandboxed` already gives the async path.
"""

from __future__ import annotations

import subprocess
import sys

from src.core.sandbox import MAX_OUTPUT_BYTES, MAX_TIMEOUT_SECONDS, run_capped


def test_stdout_is_capped():
    noisy = f"import sys; sys.stdout.write('x' * {MAX_OUTPUT_BYTES * 2})"

    result = run_capped([sys.executable, "-c", noisy], capture_output=True, text=True)

    assert len(result.stdout) < MAX_OUTPUT_BYTES * 2
    assert "truncated" in result.stdout


def test_stderr_is_capped():
    noisy = f"import sys; sys.stderr.write('e' * {MAX_OUTPUT_BYTES * 2})"

    result = run_capped([sys.executable, "-c", noisy], capture_output=True, text=True)

    assert len(result.stderr) < MAX_OUTPUT_BYTES * 2
    assert "truncated" in result.stderr


def test_ordinary_output_is_untouched():
    result = run_capped([sys.executable, "-c", "print('hello')"], capture_output=True, text=True)

    assert result.stdout.strip() == "hello"
    assert result.returncode == 0


def test_the_parent_environment_is_not_inherited(monkeypatch):
    """A secret in the service's own environment must not reach the child."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "super-secret")
    probe = "import os; print(os.environ.get('INTERNAL_SERVICE_TOKEN', 'absent'))"

    result = run_capped([sys.executable, "-c", probe], capture_output=True, text=True)

    assert result.stdout.strip() == "absent"


def test_a_caller_cannot_ask_for_an_unbounded_timeout():
    """The clamp is server-side: a model-supplied timeout cannot exceed it."""
    result = run_capped(
        [sys.executable, "-c", "print(1)"],
        capture_output=True,
        text=True,
        timeout=MAX_TIMEOUT_SECONDS * 10,
    )

    assert result.returncode == 0


def test_a_timeout_still_raises_so_callers_keep_their_handling():
    forever = "import time; time.sleep(30)"

    try:
        run_capped([sys.executable, "-c", forever], capture_output=True, text=True, timeout=1)
    except subprocess.TimeoutExpired:
        return
    raise AssertionError("a process past its timeout should raise TimeoutExpired")
