"""Child-process loop that owns one warm mermaidx (QuickJS) engine.

The renderer launches this file as a standalone script (``python -I <path>``),
not through ``multiprocessing`` ``spawn``: ``spawn`` re-executes the parent's
``__main__``, which in production is ``app.py`` and would build the whole
FastAPI app inside every worker. Run as a script, the child imports only the
standard library and mermaidx, so it must never import application packages,
and the parent never imports this module either.

Protocol: length-prefixed byte frames (``Connection.send_bytes``) over the
socket whose fd is ``argv[1]``; no pickle in either direction. A frame is a
one-line JSON header, ``\\n``, then a raw body.

- child -> parent, once: ``{"status": "ready"}`` or ``{"status": "fatal", "message": ...}``
- parent -> child: ``{"op": "validate" | "png", "scale": float}`` + UTF-8 source
- child -> parent: ``{"status": "ok"}`` + PNG bytes (empty for validate), or
  ``{"status": "error", "message": engine_message}``

EOF on the socket means the parent is gone.
"""

from __future__ import annotations

import json
from multiprocessing.connection import Connection
import os
import signal
import sys
from typing import Any

WARMUP_SOURCE = "flowchart LR\n  A --> B"
# The parent bounds source length long before this; the cap only stops a
# corrupted length prefix from allocating unbounded memory.
_MAX_REQUEST_BYTES = 16 * 1024 * 1024
_PR_SET_PDEATHSIG = 1


def encode_frame(header: dict[str, Any], body: bytes = b"") -> bytes:
    return json.dumps(header).encode() + b"\n" + body


def decode_frame(frame: bytes) -> tuple[dict[str, Any], bytes]:
    raw_header, separator, body = frame.partition(b"\n")
    header = json.loads(raw_header) if separator else None
    if not isinstance(header, dict):
        raise ValueError("malformed frame header")
    return header, body


def serve(conn: Connection, theme: str, config: dict[str, Any]) -> None:
    from mermaidx import Diagram

    try:
        # Pay the QuickJS cold start (~0.7 s) before accepting work so the
        # first real request is measured against a warm engine.
        Diagram(WARMUP_SOURCE, theme=theme, config=config).svg()
        conn.send_bytes(encode_frame({"status": "ready"}))
    except Exception as exc:  # engine could not start at all
        conn.send_bytes(encode_frame({"status": "fatal", "message": str(exc)}))
        return

    while True:
        try:
            header, body = decode_frame(conn.recv_bytes(_MAX_REQUEST_BYTES))
        except (EOFError, OSError, ValueError):
            return
        # Decode before entering the engine try: a decoding failure is a
        # protocol error, not a Mermaid parse error, and must not be reported
        # as if the user's diagram were broken.
        try:
            source = body.decode()
        except UnicodeDecodeError:
            try:
                conn.send_bytes(encode_frame({"status": "error", "message": "request body is not UTF-8"}))
            except OSError:
                return
            continue
        try:
            diagram = Diagram(source, theme=theme, config=config)
            if header.get("op") == "validate":
                diagram.svg()
                reply = encode_frame({"status": "ok"})
            else:
                reply = encode_frame({"status": "ok"}, diagram.png(scale=float(header["scale"])))
        except Exception as exc:  # Mermaid parse/layout errors surface as RuntimeError
            reply = encode_frame({"status": "error", "message": str(exc)})
        try:
            conn.send_bytes(reply)
        except OSError:  # parent went away mid-render
            return


def _die_with_parent(parent_pid: int) -> None:
    """Get SIGKILLed if the parent dies, so a long render cannot outlive it.

    Linux only (``prctl``); elsewhere the EOF check between requests is the
    only guard. The ``getppid`` check closes the race where the parent died
    before ``prctl`` ran. The signal tracks the *thread* that spawned us, which
    is why the renderer launches workers only from its own long-lived threads.
    """
    if sys.platform.startswith("linux"):
        try:
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
        except (OSError, AttributeError):
            pass
    if os.getppid() != parent_pid:
        os._exit(0)


def main(argv: list[str]) -> None:
    fd, parent_pid, theme, config_json = argv
    _die_with_parent(int(parent_pid))
    conn = Connection(int(fd))
    try:
        serve(conn, theme, json.loads(config_json))
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1:])
