"""The mermaidx adapter validates and renders in killable worker processes.

These tests drive the real mermaidx engine (about 1-3 s each) because the
contract under test is the process isolation itself: timeouts must kill and
recycle the worker, closing the renderer must not leak child processes, and a
worker must never outlive its parent or see the parent's secrets.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import pickle
import signal
import subprocess
import sys
import threading
import time

import pytest
import pytest_asyncio

from core.types.diagrams import (
    DiagramRenderError,
    DiagramRendererUnavailable,
    DiagramRenderTimeout,
    diagnostic_from_error,
)
from infrastructure.diagrams import mermaidx_renderer
from infrastructure.diagrams.mermaidx_renderer import MermaidxDiagramRenderer, _Worker

VALID = "flowchart LR\n  A[Başvuru] --> B[Belge kontrolü]"
OTHER = "flowchart TD\n  X[Onay] --> Y[Arşiv]"
INVALID = "flowchart LR\n  A --> B\n  B -->> C"
# Dense enough to keep the engine busy for several seconds (about 7 s here).
SLOW = "flowchart TD\n" + "".join(f"  N{i} --> N{(i * 7 + 3) % 45}\n" for i in range(45))
PNG_MAGIC = b"\x89PNG"


@pytest_asyncio.fixture
async def renderer():
    instance = MermaidxDiagramRenderer(workers=1, timeout_seconds=15, max_source_chars=5000)
    yield instance
    await instance.aclose()


def _record_spawns(monkeypatch: pytest.MonkeyPatch) -> list[subprocess.Popen[bytes]]:
    spawned: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(mermaidx_renderer.subprocess, "Popen", recording_popen)
    return spawned


def _assert_reaped(pid: int) -> None:
    """Our own child is gone *and* waited for (a zombie would still accept signal 0)."""
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def _is_gone(pid: int) -> bool:
    """A process we do not parent: exited, or a zombie awaiting its new reaper."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].startswith("Z")
    except (FileNotFoundError, IndexError):
        return True


def _fake_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, startup_reply: bytes, prelude: str = "") -> None:
    script = tmp_path / "fake_worker.py"
    script.write_text(
        "import os, sys, time\n"
        "from multiprocessing.connection import Connection\n"
        f"{prelude}\n"
        "conn = Connection(int(sys.argv[1]))\n"
        f"conn.send_bytes({startup_reply!r})\n"
        "time.sleep(60)\n"
    )
    monkeypatch.setattr(mermaidx_renderer, "_WORKER_SCRIPT", str(script))


def _python_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}


@pytest.mark.asyncio
async def test_valid_source_validates_and_renders_png(renderer) -> None:
    assert await renderer.validate(VALID) is None
    png = await renderer.render_png(VALID, scale=2)
    assert png.startswith(PNG_MAGIC)


@pytest.mark.asyncio
async def test_parse_error_yields_line_diagnostic(renderer) -> None:
    diagnostic = await renderer.validate(INVALID)
    assert diagnostic is not None and diagnostic.line == 3
    with pytest.raises(DiagramRenderError):
        await renderer.render_png(INVALID)


@pytest.mark.asyncio
async def test_oversized_source_is_rejected_without_a_worker_call(renderer) -> None:
    diagnostic = await renderer.validate("flowchart LR\n" + "  A --> B\n" * 1000)
    assert diagnostic is not None and "too long" in diagnostic.message
    assert renderer._workers[0].pid is None  # no worker was ever started


@pytest.mark.asyncio
async def test_timeout_kills_and_reaps_the_worker_and_next_call_respawns(renderer) -> None:
    assert await renderer.validate(VALID) is None  # warm, so the 1 ms budget always loses to a real render
    old_pid = renderer._workers[0].pid
    assert old_pid is not None

    renderer._timeout_seconds = 0.001
    with pytest.raises(DiagramRenderTimeout):
        await renderer.render_png(VALID)
    _assert_reaped(old_pid)

    renderer._timeout_seconds = 15  # the recycled worker must serve normally
    assert (await renderer.render_png(VALID)).startswith(PNG_MAGIC)
    assert renderer._workers[0].pid not in (None, old_pid)


@pytest.mark.asyncio
async def test_cancelled_call_keeps_its_worker_until_the_round_trip_ends(renderer, monkeypatch) -> None:
    assert await renderer.validate(VALID) is None  # warm: no second process can hide a shared worker
    pid = renderer._workers[0].pid
    entered, gate = threading.Event(), threading.Event()
    counter_lock = threading.Lock()
    active = peak = 0
    real_call = _Worker.call

    def gated_call(self, *args, **kwargs):
        nonlocal active, peak
        with counter_lock:
            active += 1
            peak = max(peak, active)
        try:
            if not entered.is_set():
                entered.set()
                gate.wait(10)
            return real_call(self, *args, **kwargs)
        finally:
            with counter_lock:
                active -= 1

    monkeypatch.setattr(_Worker, "call", gated_call)

    first = asyncio.create_task(renderer.render_png(VALID))
    assert await asyncio.to_thread(entered.wait, 10)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    second = asyncio.create_task(renderer.render_png(OTHER))
    await asyncio.sleep(0.3)
    assert not second.done()  # still waiting: the only worker is busy with the cancelled request
    gate.set()
    png = await second

    assert png.startswith(PNG_MAGIC)
    assert peak == 1, "two requests shared one worker connection"
    assert renderer._workers[0].pid == pid


def test_one_renderer_serves_callers_on_different_event_loops() -> None:
    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=15, max_source_chars=5000)

    async def contended_burst():
        # Two callers for one worker, so the second one has to wait on this loop.
        return await asyncio.gather(renderer.validate(VALID), renderer.validate(INVALID))

    try:
        for _ in range(2):  # each asyncio.run() is a fresh loop, like pytest or a sync wrapper
            valid, invalid = asyncio.run(contended_burst())
            assert valid is None
            assert invalid is not None and invalid.line == 3
    finally:
        asyncio.run(renderer.aclose())


@pytest.mark.asyncio
async def test_aclose_reaps_the_worker_process() -> None:
    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=15, max_source_chars=5000)
    assert await renderer.validate(VALID) is None
    pid = renderer._workers[0].pid
    assert pid is not None
    await renderer.aclose()
    _assert_reaped(pid)


@pytest.mark.asyncio
async def test_calls_after_aclose_are_refused_without_spawning(monkeypatch) -> None:
    spawned = _record_spawns(monkeypatch)
    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=15, max_source_chars=5000)
    assert await renderer.validate(VALID) is None
    await renderer.aclose()

    with pytest.raises(DiagramRendererUnavailable):
        await renderer.validate(VALID)
    assert len(spawned) == 1


@pytest.mark.asyncio
async def test_worker_starting_during_aclose_is_killed_not_published(monkeypatch) -> None:
    spawned = _record_spawns(monkeypatch)
    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=15, max_source_chars=5000)
    pending = asyncio.create_task(renderer.validate(VALID))
    deadline = time.monotonic() + 10
    while not spawned and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert spawned, "the worker was never launched"

    await renderer.aclose()  # the child is still in its ~0.7 s cold start

    with pytest.raises(DiagramRendererUnavailable):
        await pending
    assert renderer._workers[0].pid is None
    _assert_reaped(spawned[0].pid)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "startup_reply",
    [b"not a frame", pickle.dumps(("ready", None))],
    ids=["garbage", "pickle"],
)
async def test_malformed_startup_reply_reaps_the_worker(monkeypatch, tmp_path, startup_reply) -> None:
    _fake_worker(tmp_path, monkeypatch, startup_reply)
    spawned = _record_spawns(monkeypatch)
    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=2, max_source_chars=5000)
    try:
        with pytest.raises(DiagramRendererUnavailable) as raised:
            await renderer.validate(VALID)
        assert not isinstance(raised.value, DiagramRenderTimeout), "the reply must be rejected at startup"
        assert renderer._workers[0].pid is None
        _assert_reaped(spawned[0].pid)
    finally:
        await renderer.aclose()


@pytest.mark.asyncio
async def test_worker_environment_carries_no_parent_secrets(monkeypatch, tmp_path) -> None:
    env_dump = tmp_path / "env.json"
    _fake_worker(
        tmp_path,
        monkeypatch,
        b"not a frame",
        prelude=f"import json\nopen({str(env_dump)!r}, 'w').write(json.dumps(sorted(os.environ)))",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-parent-secret")
    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=2, max_source_chars=5000)
    try:
        with pytest.raises(DiagramRendererUnavailable):
            await renderer.validate(VALID)
    finally:
        await renderer.aclose()

    child_env = set(json.loads(env_dump.read_text()))
    assert "OPENAI_API_KEY" not in child_env
    assert child_env <= {"PATH", "LANG", "LC_ALL", "LC_CTYPE"}


def test_worker_dies_with_its_parent_even_mid_render() -> None:
    parent_code = (
        "import asyncio, sys\n"
        "from infrastructure.diagrams.mermaidx_renderer import MermaidxDiagramRenderer\n"
        "async def main():\n"
        "    renderer = MermaidxDiagramRenderer(workers=1, timeout_seconds=120, max_source_chars=50000)\n"
        "    await renderer.validate('flowchart LR\\n  A --> B')\n"
        "    print(f'WORKER_PID={renderer._workers[0].pid}', flush=True)\n"
        "    await renderer.render_png(sys.argv[1])\n"
        "asyncio.run(main())\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code, SLOW],
        env=_python_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    worker_pid: int | None = None
    try:
        assert parent.stdout is not None
        for line in parent.stdout:
            if line.startswith("WORKER_PID="):
                worker_pid = int(line.removeprefix("WORKER_PID="))
                break
        assert worker_pid is not None, "the parent never reported its worker"
        time.sleep(1.0)  # the SLOW render is now in flight inside the worker

        parent.send_signal(signal.SIGKILL)
        parent.wait(timeout=10)

        deadline = time.monotonic() + 3  # well short of the remaining render time
        while not _is_gone(worker_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _is_gone(worker_pid), "the worker outlived its parent"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        if worker_pid is not None and not _is_gone(worker_pid):
            os.kill(worker_pid, signal.SIGKILL)


def test_parent_never_imports_the_worker_module() -> None:
    probe = (
        "import sys\n"
        "import infrastructure.diagrams.mermaidx_renderer\n"
        "print('WORKER_IMPORTED=' + str('infrastructure.diagrams.mermaid_worker' in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], env=_python_env(), capture_output=True, text=True, timeout=60, check=True
    )
    assert "WORKER_IMPORTED=False" in result.stdout


def test_diagnostic_parser_extracts_line() -> None:
    text = "Mermaid rendering failed: Error: Parse error on line 3:\n...B -->> C\n---^\nExpecting 'AMP'"
    diagnostic = diagnostic_from_error(text)
    assert diagnostic.line == 3
    assert diagnostic.message.startswith("Parse error on line 3")
