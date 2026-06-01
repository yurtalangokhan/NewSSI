"""
Airbyte Destination → Embedding API.

A lightweight custom Airbyte destination connector that streams records
from **any** Airbyte source directly to agent-service's batch ingestion
endpoint.  Records are buffered in memory in configurable batches and
POSTed over HTTP — **zero** disk I/O, **bounded** RAM usage.

Implements the Airbyte Destination protocol v0 (stdin JSON-lines):
  • spec          → print JSON spec to stdout
  • check         → validate connectivity to agent-service
  • write         → read AirbyteRecordMessages from stdin, batch & POST

Memory model:
  At most ``batch_size`` records (~200 by default) are held in RAM.
  Each batch is flushed to agent-service before the next is started,
  so peak memory is O(batch_size × avg_record_size).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import requests

logger = logging.getLogger("destination_embedding")

SPEC_PATH = Path(__file__).parent / "spec.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _emit(message: dict[str, Any]) -> None:
    """Write a single Airbyte protocol message to stdout."""
    print(json.dumps(message), flush=True)


def _emit_log(level: str, msg: str) -> None:
    _emit({
        "type": "LOG",
        "log": {"level": level, "message": msg},
    })


def _emit_state(state_data: dict[str, Any]) -> None:
    _emit({
        "type": "STATE",
        "state": {"data": state_data},
    })


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

def cmd_spec() -> None:
    """Output the connector specification."""
    spec = _load_json_file(str(SPEC_PATH))
    _emit({"type": "SPEC", "spec": spec})


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def cmd_check(config: dict[str, Any]) -> None:
    """Test connectivity to agent-service."""
    base_url = config["agent_service_url"].rstrip("/")
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        if resp.status_code < 400:
            _emit({
                "type": "CONNECTION_STATUS",
                "connectionStatus": {"status": "SUCCEEDED"},
            })
        else:
            _emit({
                "type": "CONNECTION_STATUS",
                "connectionStatus": {
                    "status": "FAILED",
                    "message": f"Agent-service returned HTTP {resp.status_code}",
                },
            })
    except Exception as exc:
        _emit({
            "type": "CONNECTION_STATUS",
            "connectionStatus": {
                "status": "FAILED",
                "message": f"Cannot reach agent-service: {exc}",
            },
        })


# ---------------------------------------------------------------------------
# Write (streaming batch pipeline)
# ---------------------------------------------------------------------------

class _BatchWriter:
    """Buffers records and flushes to agent-service in batches.

    Memory guarantee:  at most ``batch_size`` dicts in ``_buffer``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._base_url = config["agent_service_url"].rstrip("/")
        self._datasource_id: str = config["datasource_id"]
        self._connector_type: str = str(config.get("connector_type", "unknown"))
        self._batch_size: int = int(config.get("batch_size", 200))
        self._timeout: int = int(config.get("request_timeout_seconds", 120))
        self._buffer: list[dict[str, Any]] = []
        self._total_sent: int = 0
        self._batch_index: int = 0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ---- public API ------------------------------------------------------

    def add_record(self, stream: str, data: dict[str, Any]) -> None:
        """Buffer a single record.  Flushes automatically at batch_size."""
        data["_stream"] = stream
        self._buffer.append(data)
        if len(self._buffer) >= self._batch_size:
            self._flush(is_last=False)

    def finalize(self) -> int:
        """Flush remaining records and signal completion.  Returns total sent."""
        if self._buffer:
            self._flush(is_last=True)
        else:
            # Send empty final signal so agent-service knows sync is done
            self._flush(is_last=True)
        return self._total_sent

    # ---- internals -------------------------------------------------------

    def _flush(self, is_last: bool) -> None:
        batch = self._buffer
        self._buffer = []  # release memory immediately
        stream_name = str(batch[0].get("_stream", "unknown")) if batch else "unknown"

        payload = {
            "datasource_id": self._datasource_id,
            "connector_type": self._connector_type,
            "stream_name": stream_name,
            "batch_id": f"{self._datasource_id}:{self._batch_index}",
            "records": batch,
            "batch_index": self._batch_index,
            "is_last_batch": is_last,
        }

        batch_path = "/batch"
        retries = 3
        for attempt in range(1, retries + 1):
            try:
                resp = self._session.post(
                    f"{self._base_url}{batch_path}",
                    data=json.dumps(payload),
                    timeout=self._timeout,
                )
                if resp.status_code < 400:
                    result = resp.json()
                    indexed = result.get("chunks_indexed", 0)
                    self._total_sent += len(batch)
                    self._batch_index += 1
                    _emit_log(
                        "INFO",
                        f"Batch {self._batch_index}: sent {len(batch)} records, "
                        f"indexed {indexed} chunks (total {self._total_sent} records)",
                    )
                    return
                else:
                    _emit_log(
                        "WARN",
                        f"Batch POST to {batch_path} returned {resp.status_code}: {resp.text[:300]} "
                        f"(attempt {attempt}/{retries})",
                    )
            except requests.RequestException as exc:
                _emit_log(
                    "WARN",
                    f"Batch POST failed (attempt {attempt}/{retries}): {exc}",
                )

            if attempt < retries:
                time.sleep(2 ** (attempt - 1))

        # All retries exhausted
        raise RuntimeError(
            f"Failed to POST batch {self._batch_index} after {retries} attempts"
        )


def cmd_write(config: dict[str, Any], catalog: dict[str, Any], input_stream: TextIO) -> None:
    """Read Airbyte protocol messages from stdin and stream batches."""
    writer = _BatchWriter(config)

    _emit_log("INFO", f"destination-embedding started (batch_size={config.get('batch_size', 200)})")
    _emit_log("INFO", f"Target: {config['agent_service_url']} / datasource {config['datasource_id']}")

    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = message.get("type", "")

        if msg_type == "RECORD":
            record = message.get("record", {})
            stream = record.get("stream", "unknown")
            data = record.get("data", {})
            if isinstance(data, dict):
                writer.add_record(stream, data)

        elif msg_type == "STATE":
            # Flush current buffer before acknowledging state
            if writer._buffer:
                writer._flush(is_last=False)
            # Echo state back to confirm progress
            _emit_state(message.get("state", {}).get("data", {}))

        # Ignore CATALOG, LOG, TRACE, etc.

    total = writer.finalize()
    _emit_log("INFO", f"destination-embedding completed: {total} records streamed")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    args = sys.argv[1:]
    if not args:
        print("Usage: destination-embedding <command> [--config <path>] [--catalog <path>]", file=sys.stderr)
        sys.exit(1)

    command = args[0]

    # Parse --config and --catalog flags
    config_path: str | None = None
    catalog_path: str | None = None
    for i, arg in enumerate(args):
        if arg == "--config" and i + 1 < len(args):
            config_path = args[i + 1]
        elif arg == "--catalog" and i + 1 < len(args):
            catalog_path = args[i + 1]

    if command == "spec":
        cmd_spec()

    elif command == "check":
        if not config_path:
            print("--config required for check", file=sys.stderr)
            sys.exit(1)
        config = _load_json_file(config_path)
        cmd_check(config)

    elif command == "write":
        if not config_path:
            print("--config required for write", file=sys.stderr)
            sys.exit(1)
        config = _load_json_file(config_path)
        catalog = _load_json_file(catalog_path) if catalog_path else {}
        cmd_write(config, catalog, sys.stdin)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
