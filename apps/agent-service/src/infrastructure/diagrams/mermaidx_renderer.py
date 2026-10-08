"""In-process Mermaid rendering through mermaidx, isolated in worker processes.

mermaidx runs Mermaid inside QuickJS with no time or memory limit, and a thread
cannot be killed, so every render runs in a dedicated child process that this
adapter can kill on timeout and respawn transparently.

- Launch: a plain ``subprocess`` runs ``mermaid_worker.py`` as a script in
  isolated mode with a minimal environment (no app secrets). The parent never
  imports that module; see it for why ``multiprocessing`` ``spawn`` is avoided.
- Wire: length-prefixed byte frames over a socketpair (JSON header + raw body),
  so the parent never unpickles anything the child sends.
- Pool: one ``ThreadPoolExecutor`` thread per worker. Waiting callers queue in
  the executor, which is not bound to any event loop, and a cancelled caller
  cannot hand back a worker whose round trip is still running, because the
  pool thread itself releases it. Only these long-lived threads spawn workers,
  which keeps the child's parent-death signal (tied to the spawning thread)
  valid for the renderer's lifetime.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
import json
from multiprocessing.connection import Connection
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
from typing import Any

from core.observability.logger import get_logger
from core.types.diagrams import (
    DiagramDiagnostic,
    DiagramRenderError,
    DiagramRendererUnavailable,
    DiagramRenderTimeout,
    diagnostic_from_error,
)

logger = get_logger(__name__)

_WORKER_SCRIPT = str(Path(__file__).with_name("mermaid_worker.py"))
# Everything the child needs: it only runs this interpreter's stdlib + mermaidx.
_WORKER_ENV = {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
_STARTUP_TIMEOUT_SECONDS = 30.0
_REAP_TIMEOUT_SECONDS = 5.0
_MAX_REPLY_BYTES = 64 * 1024 * 1024
_MAX_EDGES = 500
_REPLY_STATUSES = frozenset({"ready", "fatal", "ok", "error"})

_Request = tuple[str, str, float]
_Reply = tuple[str, bytes | str]


def _encode_frame(header: dict[str, Any], body: bytes = b"") -> bytes:
    """Mirror of ``mermaid_worker.encode_frame``; duplicated so the parent never imports the worker."""
    return json.dumps(header).encode() + b"\n" + body


def _decode_reply(frame: bytes) -> tuple[str, str | None, bytes]:
    raw_header, separator, body = frame.partition(b"\n")
    header = json.loads(raw_header) if separator else None
    if not isinstance(header, dict):
        raise ValueError("malformed mermaid worker frame")
    status, message = header.get("status"), header.get("message")
    if status not in _REPLY_STATUSES or not (message is None or isinstance(message, str)):
        raise ValueError(f"unexpected mermaid worker reply header: {header!r:.200}")
    return status, message, body


class _Worker:
    """One child process and its connection; every method blocks, call it from a thread."""

    def __init__(self, theme: str, config: dict[str, Any]) -> None:
        self._argv_tail = [theme, json.dumps(config)]
        self._lock = threading.Lock()
        self._closed = False
        self._process: subprocess.Popen[bytes] | None = None
        self._conn: Connection | None = None

    @property
    def pid(self) -> int | None:
        process = self._process
        return process.pid if process is not None else None

    def _launch(self) -> tuple[subprocess.Popen[bytes], Connection]:
        parent_sock, child_sock = socket.socketpair()
        child_fd = child_sock.fileno()
        with self._lock:
            try:
                if self._closed:
                    raise DiagramRendererUnavailable("diagram renderer is closed")
                # -I: no PYTHON* env, no user site, script dir off sys.path. A new
                # session keeps the child out of the terminal's process group, so
                # Ctrl-C reaches only the parent, which closes workers on shutdown.
                process = subprocess.Popen(  # noqa: S603 - fixed argv: this interpreter and our own worker script
                    [sys.executable, "-I", _WORKER_SCRIPT, str(child_fd), str(os.getpid()), *self._argv_tail],
                    pass_fds=(child_fd,),
                    stdin=subprocess.DEVNULL,
                    env=_WORKER_ENV,
                    start_new_session=True,
                )
            except BaseException as exc:
                parent_sock.close()
                if isinstance(exc, OSError):
                    raise DiagramRendererUnavailable(f"mermaid worker could not be launched: {exc}") from exc
                raise
            finally:
                child_sock.close()
            # Published before the handshake so close() can kill a worker that is still starting.
            self._process = process
        return process, Connection(parent_sock.detach())

    def _start(self) -> Connection:
        process, conn = self._launch()
        try:
            if not conn.poll(_STARTUP_TIMEOUT_SECONDS):
                raise DiagramRendererUnavailable("mermaid worker did not start in time")
            status, message, _ = _decode_reply(conn.recv_bytes(_MAX_REPLY_BYTES))
            if status != "ready":
                raise DiagramRendererUnavailable(f"mermaid worker failed to start: {message}")
            with self._lock:
                if self._closed:
                    raise DiagramRendererUnavailable("diagram renderer closed while the worker was starting")
                self._conn = conn
        except BaseException as exc:
            with self._lock:
                if self._process is process:
                    self._process = None
            _reap(process, conn)
            if isinstance(exc, DiagramRendererUnavailable) or not isinstance(exc, Exception):
                raise
            raise DiagramRendererUnavailable(f"mermaid worker failed during startup: {exc}") from exc
        return conn

    def call(self, request: _Request, timeout: float) -> _Reply:
        """Blocking round trip; the renderer runs it on its own pool thread."""
        op, source, scale = request
        conn, process = self._conn, self._process
        if conn is None or process is None or process.poll() is not None:
            self.kill()
            conn = self._start()
        # ``poll`` only waits for the *first* byte of the reply. A worker that
        # stalls part-way through a large PNG would block the pool thread
        # forever, so a watchdog kills it: the killed socket returns EOF and
        # the read below unblocks.
        timed_out = threading.Event()
        watchdog = threading.Timer(timeout, self._abort_on_timeout, args=(process, timed_out))
        watchdog.daemon = True
        watchdog.start()
        try:
            conn.send_bytes(_encode_frame({"op": op, "scale": scale}, source.encode()))
            if not conn.poll(timeout):
                self.kill()
                timed_out.set()
                logger.warning("Mermaid render exceeded %ss; worker recycled", timeout)
                raise DiagramRenderTimeout(f"diagram render exceeded {timeout}s")
            status, message, body = _decode_reply(conn.recv_bytes(_MAX_REPLY_BYTES))
            if status not in {"ok", "error"}:
                raise ValueError(f"unexpected mermaid worker status {status!r}")
        except (EOFError, OSError, ValueError) as exc:
            self.kill()
            if timed_out.is_set():
                logger.warning("Mermaid render exceeded %ss while reading the reply", timeout)
                raise DiagramRenderTimeout(f"diagram render exceeded {timeout}s") from exc
            logger.warning("Mermaid worker failed: %s", exc)
            raise DiagramRendererUnavailable(f"mermaid worker failed: {exc}") from exc
        finally:
            watchdog.cancel()
        return (status, body) if status == "ok" else (status, message or "")

    def _abort_on_timeout(self, process: subprocess.Popen[bytes], timed_out: threading.Event) -> None:
        """Watchdog body: flag the timeout and make the blocked read fail."""
        timed_out.set()
        if process.poll() is None:
            process.kill()

    def close(self) -> None:
        """Refuse new work and SIGKILL the child; never blocks, so it is safe on the event loop.

        A pool thread mid-call then sees EOF and cleans up the connection itself.
        """
        with self._lock:
            self._closed = True
            process = self._process
        if process is not None and process.poll() is None:
            process.kill()

    def kill(self) -> None:
        with self._lock:
            process, conn = self._process, self._conn
            self._process, self._conn = None, None
        _reap(process, conn)


def _reap(process: subprocess.Popen[bytes] | None, conn: Connection | None) -> None:
    if conn is not None:
        conn.close()
    if process is None:
        return
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        logger.warning("Mermaid worker pid %s did not exit after SIGKILL", process.pid)


class MermaidxDiagramRenderer:
    def __init__(self, *, workers: int, timeout_seconds: float, max_source_chars: int, theme: str = "neutral") -> None:
        self.renderer_version = f"mermaidx-{version('mermaidx')}"
        self._timeout_seconds = timeout_seconds
        self._max_source_chars = max_source_chars
        config = {"maxTextSize": max_source_chars, "maxEdges": _MAX_EDGES}
        self._workers = [_Worker(theme, config) for _ in range(max(1, workers))]
        self._idle: queue.SimpleQueue[_Worker] = queue.SimpleQueue()
        for worker in self._workers:
            self._idle.put(worker)
        self._executor = ThreadPoolExecutor(max_workers=len(self._workers), thread_name_prefix="mermaid-render")
        self._closed = False

    def _too_long(self, source: str) -> DiagramDiagnostic | None:
        if len(source) > self._max_source_chars:
            return DiagramDiagnostic(
                line=None, message=f"diagram source too long ({len(source)} > {self._max_source_chars} chars)"
            )
        return None

    def _run(self, request: _Request) -> _Reply:
        worker = self._idle.get()  # never waits: the pool has exactly one thread per worker
        try:
            return worker.call(request, self._timeout_seconds)
        finally:
            self._idle.put(worker)

    async def _call(self, op: str, source: str, scale: float) -> _Reply:
        if self._closed:
            raise DiagramRendererUnavailable("diagram renderer is closed")
        try:
            future = asyncio.get_running_loop().run_in_executor(self._executor, self._run, (op, source, scale))
        except RuntimeError as exc:  # the pool was shut down after the check above
            raise DiagramRendererUnavailable("diagram renderer is closed") from exc
        try:
            return await future
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if self._closed and not (task is not None and task.cancelling()):
                # aclose() dropped this queued request; the caller was not cancelled.
                raise DiagramRendererUnavailable("diagram renderer is closed") from None
            raise

    async def validate(self, source: str) -> DiagramDiagnostic | None:
        oversized = self._too_long(source)
        if oversized:
            return oversized
        status, payload = await self._call("validate", source, 1.0)
        return diagnostic_from_error(str(payload)) if status == "error" else None

    async def render_png(self, source: str, *, scale: float = 3.0) -> bytes:
        oversized = self._too_long(source)
        if oversized:
            raise DiagramRenderError(oversized)
        status, payload = await self._call("png", source, scale)
        if status == "error":
            raise DiagramRenderError(diagnostic_from_error(str(payload)))
        if not isinstance(payload, bytes):
            raise DiagramRendererUnavailable("mermaid worker returned no image")
        return payload

    async def aclose(self) -> None:
        self._closed = True
        for worker in self._workers:
            worker.close()
        await asyncio.to_thread(self._shutdown)

    def _shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        for worker in self._workers:
            worker.kill()
