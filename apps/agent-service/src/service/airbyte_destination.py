"""
Airbyte Destination Reader.

Reads sync output from Airbyte's destination after a sync job completes.
Supports ``local-json`` mode (shared Docker volume with JSONL files).

This module bridges Airbyte sync output → the existing ingestion pipeline,
ensuring records are returned in the same format that the old PyAirbyte
``extract_data()`` produced.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Base path where Airbyte worker writes local-json output
_OUTPUT_BASE = Path(os.environ.get("AIRBYTE_LOCAL_OUTPUT_PATH", "/tmp/airbyte_local"))


class AirbyteDestinationReader:
    """Read records produced by Airbyte sync jobs."""

    def __init__(self, output_base: Path | None = None) -> None:
        self._base = output_base or _OUTPUT_BASE

    # ---- public API ------------------------------------------------------

    async def read_sync_output(
        self,
        connection_id: str | None = None,
        job_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read all records from Airbyte local-json destination output.

        Scans the output directory for ``.jsonl`` files produced by the
        sync job and returns a flat list of record dicts.  Each record
        has a ``_stream`` key injected so the ingestion pipeline can
        identify the source stream.

        The returned shape is identical to the previous PyAirbyte
        ``extract_data()`` output — ensuring ``ingestion.py`` compatibility.
        """
        records: list[dict[str, Any]] = []

        if not self._base.exists():
            logger.warning("Airbyte output directory does not exist: %s", self._base)
            return records

        # Airbyte local-json writes files under:
        #   <output_base>/<stream_name>/_airbyte_raw_<stream_name>.jsonl
        # or sometimes just:
        #   <output_base>/<stream_name>.jsonl
        # We scan recursively for all .jsonl files.

        jsonl_files = sorted(self._base.rglob("*.jsonl"))
        if not jsonl_files:
            # Also try .json files
            jsonl_files = sorted(self._base.rglob("*.json"))

        logger.info(
            "Found %d output file(s) in %s", len(jsonl_files), self._base
        )

        for fpath in jsonl_files:
            stream_name = self._infer_stream_name(fpath)
            try:
                file_records = self._read_jsonl_file(fpath, stream_name)
                records.extend(file_records)
            except Exception:
                logger.exception("Error reading output file: %s", fpath)

        logger.info("Read %d total records from Airbyte output", len(records))
        return records

    async def cleanup_sync_output(
        self,
        connection_id: str | None = None,
        job_id: int | None = None,
    ) -> None:
        """Delete processed output files to prevent disk bloat."""
        if not self._base.exists():
            return

        count = 0
        for fpath in self._base.rglob("*.jsonl"):
            try:
                fpath.unlink()
                count += 1
            except OSError as e:
                logger.warning("Could not delete %s: %s", fpath, e)

        for fpath in self._base.rglob("*.json"):
            try:
                fpath.unlink()
                count += 1
            except OSError as e:
                logger.warning("Could not delete %s: %s", fpath, e)

        # Remove empty directories
        for dirpath in sorted(self._base.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    dirpath.rmdir()  # Only succeeds if empty
                except OSError:
                    pass

        logger.info("Cleaned up %d output file(s) from %s", count, self._base)

    # ---- internals -------------------------------------------------------

    def _infer_stream_name(self, fpath: Path) -> str:
        """Guess the stream name from the file path.

        Typical patterns:
        * ``<base>/<stream>/_airbyte_raw_<stream>.jsonl``
        * ``<base>/<stream>.jsonl``
        """
        relative = fpath.relative_to(self._base)
        parts = relative.parts

        if len(parts) >= 2:
            # Subdirectory name is the stream name
            return parts[0]
        else:
            # File name is the stream name
            stem = fpath.stem
            # Strip _airbyte_raw_ prefix if present
            if stem.startswith("_airbyte_raw_"):
                return stem[len("_airbyte_raw_"):]
            return stem

    def _read_jsonl_file(
        self,
        fpath: Path,
        stream_name: str,
    ) -> list[dict[str, Any]]:
        """Parse a JSONL file into a list of record dicts."""
        records: list[dict[str, Any]] = []

        with open(fpath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON on line %d of %s", line_num, fpath)
                    continue

                # Airbyte raw records have an _airbyte_data field
                if "_airbyte_data" in raw:
                    record = raw["_airbyte_data"]
                elif "data" in raw:
                    record = raw["data"]
                else:
                    # Treat the whole line as the record
                    record = raw

                if isinstance(record, dict):
                    record["_stream"] = stream_name
                    records.append(record)

        logger.debug(
            "Read %d records from %s (stream=%s)",
            len(records), fpath.name, stream_name,
        )
        return records


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_INSTANCE: AirbyteDestinationReader | None = None


def get_destination_reader() -> AirbyteDestinationReader:
    """Return the global destination reader singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AirbyteDestinationReader()
    return _INSTANCE
