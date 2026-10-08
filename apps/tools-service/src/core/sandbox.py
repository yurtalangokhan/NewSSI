"""Bounded subprocess execution.

Every process the service starts on behalf of a model goes through here:
argv only (never a shell string — a blocklist over free-form shell text is
not a security boundary; see spec TS-1), its own process group so a
timeout kills grandchildren instead of leaving them running, resource
limits, a minimal environment, and a hard output cap.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
from typing import Any

from config_manager import env

try:
    import resource
except ImportError:  # Windows can host the service, but not the POSIX sandbox.
    resource = None  # type: ignore[assignment]  # POSIX-only stdlib module.

MAX_TIMEOUT_SECONDS = 120.0
MAX_OUTPUT_BYTES = 256_000
RLIMIT_CPU_SECONDS = 60
RLIMIT_ADDRESS_SPACE_BYTES = 2 * 1024 * 1024 * 1024
RLIMIT_FILE_SIZE_BYTES = 100 * 1024 * 1024
RLIMIT_PROCESSES = 2048
RLIMIT_OPEN_FILES = 256

# Dropping privilege from root inside the sandboxed child is a defence
# that requires the parent to actually be root and the target account to
# exist; both are deployment concerns (Task 15/19), not something this
# module can assume. EXECUTOR_UID is read here so callers gain the
# behaviour automatically once that infrastructure lands, without another
# change to this file.
EXECUTOR_UID = env.EXECUTOR_UID


@dataclass(frozen=True)
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    truncated: bool
    timed_out: bool


def _apply_limits() -> None:
    """Run in the child between fork and exec (preexec_fn)."""
    _require_posix_sandbox()
    resource.setrlimit(resource.RLIMIT_CPU, (RLIMIT_CPU_SECONDS, RLIMIT_CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (RLIMIT_ADDRESS_SPACE_BYTES, RLIMIT_ADDRESS_SPACE_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (RLIMIT_FILE_SIZE_BYTES, RLIMIT_FILE_SIZE_BYTES))
    resource.setrlimit(resource.RLIMIT_NPROC, (RLIMIT_PROCESSES, RLIMIT_PROCESSES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (RLIMIT_OPEN_FILES, RLIMIT_OPEN_FILES))
    # A new session/process group: os.killpg on timeout reaches every
    # descendant the child spawned, not just the direct child asyncio
    # tracks. Without this, subprocess.run(timeout=...)-style cleanup only
    # kills the immediate child and grandchildren keep running.
    os.setsid()
    if EXECUTOR_UID > 0 and os.geteuid() == 0:
        os.setgid(EXECUTOR_UID)
        os.setuid(EXECUTOR_UID)


def _clean_env() -> dict[str, str]:
    """A minimal environment. The parent's secrets are never inherited."""
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",  # noqa: S108 - child-process HOME inside the sandbox boundary
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _truncate(raw: bytes) -> tuple[str, bool]:
    if len(raw) <= MAX_OUTPUT_BYTES:
        return raw.decode("utf-8", errors="replace"), False
    head = raw[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return head + f"\n... [truncated at {MAX_OUTPUT_BYTES} bytes]", True


async def run_sandboxed(
    argv: list[str],
    *,
    cwd: Path,
    execution_timeout: float,
) -> SandboxResult:
    """Run argv with limits. Never accepts a shell string.

    The caller's requested timeout is clamped to MAX_TIMEOUT_SECONDS: a
    model cannot hold a sandboxed process open indefinitely just by asking
    for a larger timeout.
    """
    if not argv:
        raise ValueError("argv must not be empty")

    _require_posix_sandbox()

    effective_timeout = min(float(execution_timeout), MAX_TIMEOUT_SECONDS)

    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=_clean_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=_apply_limits,
    )

    timed_out = False
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(process.communicate(), timeout=effective_timeout)
    except TimeoutError:
        timed_out = True
        try:
            # Negative pid targets the process group created by os.setsid()
            # above, reaching grandchildren a plain process.kill() would
            # leave running.
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        stdout_raw, stderr_raw = await process.communicate()

    stdout, stdout_truncated = _truncate(stdout_raw or b"")
    stderr, stderr_truncated = _truncate(stderr_raw or b"")

    return SandboxResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=process.returncode if process.returncode is not None else -1,
        truncated=stdout_truncated or stderr_truncated,
        timed_out=timed_out,
    )


def _require_posix_sandbox() -> None:
    if resource is None:
        raise RuntimeError("Sandbox execution requires POSIX resource limits; use Linux or WSL.")


def run_capped(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """A bounded drop-in for ``subprocess.run`` for the synchronous tools.

    java_tools and git_tools are plain ``def`` tools, so they cannot await
    ``run_sandboxed``; they called ``subprocess.run`` directly and inherited
    none of its protections. This applies the same ones: the parent's
    environment (and its secrets) is not inherited, resource limits and a new
    process group are installed in the child, the caller's timeout is clamped
    server-side, and both streams are truncated at ``MAX_OUTPUT_BYTES``.

    ``TimeoutExpired`` is deliberately allowed to propagate: the call sites
    already handle it and turn it into their own tool-level error.
    """
    _require_posix_sandbox()
    kwargs.setdefault("env", _clean_env())
    kwargs.setdefault("preexec_fn", _apply_limits)
    requested = kwargs.get("timeout")
    kwargs["timeout"] = MAX_TIMEOUT_SECONDS if requested is None else min(float(requested), MAX_TIMEOUT_SECONDS)

    completed = subprocess.run(argv, **kwargs)  # noqa: S603 - argv only, never a shell string

    text_mode = kwargs.get("text") or kwargs.get("universal_newlines")
    capped_streams: list[str | bytes | None] = []
    for stream in (completed.stdout, completed.stderr):
        if stream is None:
            capped_streams.append(None)
            continue
        raw = stream.encode("utf-8", errors="replace") if text_mode else stream
        capped, _ = _truncate(raw)
        capped_streams.append(capped if text_mode else capped.encode("utf-8"))

    return subprocess.CompletedProcess(completed.args, completed.returncode, capped_streams[0], capped_streams[1])
