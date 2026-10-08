"""Spec TS-7a: run_python/run_node/run_pytest/run_npm_command/run_python_file
must execute under core.sandbox.run_sandboxed rather than a bare
subprocess.run, so a model-supplied program cannot loop forever, exhaust
memory, hold a huge output buffer, or read the service's own secrets."""

import time
from pathlib import Path

import pytest


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(tmp_path: Path, monkeypatch):
    from src.tools import code_tools

    monkeypatch.setattr(code_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    code_tools.CodeTools().register_tools(recorder)
    return recorder.tools


@pytest.mark.asyncio
async def test_infinite_loop_is_terminated(tools):
    started = time.monotonic()
    out = await tools["run_python"]("while True: pass", timeout=3)
    assert time.monotonic() - started < 20
    assert "timed out" in out.lower() or "zaman" in out.lower()


@pytest.mark.asyncio
async def test_runaway_allocation_is_terminated(tools):
    out = await tools["run_python"]("x = bytearray(8 * 1024 * 1024 * 1024)", timeout=20)
    assert "MemoryError" in out or "Exit Code" in out


@pytest.mark.asyncio
async def test_model_supplied_timeout_is_clamped(tools):
    from src.core.sandbox import MAX_TIMEOUT_SECONDS

    started = time.monotonic()
    await tools["run_python"](
        f"import time; time.sleep({MAX_TIMEOUT_SECONDS + 600})", timeout=10_000
    )
    assert time.monotonic() - started < MAX_TIMEOUT_SECONDS + 30


@pytest.mark.asyncio
async def test_secrets_are_not_visible_to_executed_code(tools, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "must-not-leak")
    out = await tools["run_python"]("import os; print(os.environ)", timeout=10)
    assert "must-not-leak" not in out


@pytest.mark.asyncio
async def test_output_is_capped(tools):
    from src.core.sandbox import MAX_OUTPUT_BYTES

    out = await tools["run_python"](f"print('x' * {MAX_OUTPUT_BYTES * 3})", timeout=30)
    assert len(out.encode("utf-8")) <= MAX_OUTPUT_BYTES + 500
    assert "truncated" in out


@pytest.mark.asyncio
async def test_run_node_is_sandboxed_and_cannot_see_secrets(tools, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "must-not-leak")
    out = await tools["run_node"]("console.log(process.env)", timeout=10)
    assert "must-not-leak" not in out


@pytest.mark.asyncio
async def test_run_python_file_timeout_is_enforced(tools, tmp_path):
    script = tmp_path / "loop.py"
    script.write_text("while True: pass", encoding="utf-8")
    started = time.monotonic()
    out = await tools["run_python_file"]("loop.py", timeout=3)
    assert time.monotonic() - started < 20
    assert "timed out" in out.lower() or "zaman" in out.lower()
