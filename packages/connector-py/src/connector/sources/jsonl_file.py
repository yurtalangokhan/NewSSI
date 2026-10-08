"""JSON Lines file source.

Reads one or more ``*.jsonl`` files from a directory; each file is a stream
named after the file stem. Supports incremental sync on a numeric or string
cursor field (e.g. ``updated_at``).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSource
from ..common.blocking import iterate_in_thread
from ..common.cursor import CursorTracker, incremental_cursor, is_newer
from ..common.json_schema import add_properties
from ..errors import CheckFailedError
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)


class JsonlFileConfig(BaseModel):
    directory: str = Field(description="Directory containing *.jsonl files. Each file is a stream.")
    glob: str = Field(default="*.jsonl", description="Glob used to find stream files.")
    cursor_field: str | None = Field(
        default=None,
        description="Optional incremental-sync field; records with a greater value are new.",
    )
    encoding: str = "utf-8"


class JsonlFileSource(BaseSource[JsonlFileConfig]):
    definition = ConnectorDefinition(
        name="jsonl_file",
        icon="jsonl_file.svg",
        display_name="JSON Lines Files",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.FILE,
        tags=frozenset({"file", "local"}),
    )
    Config = JsonlFileConfig

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def _files(self) -> list[Path]:
        return sorted(Path(self.config.directory).glob(self.config.glob))

    async def check(self) -> CheckResult:
        root = Path(self.config.directory)
        if not root.is_dir():
            return CheckResult(ok=False, message=f"{root} is not a directory")
        if not self._files():
            return CheckResult(ok=False, message=f"no files match {self.config.glob} in {root}")
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        check = await self.check()
        if not check.ok:
            raise CheckFailedError(check.message or "check failed")
        streams = []
        for path in await asyncio.to_thread(self._files):
            modes = [SyncMode.FULL_REFRESH]
            cursor: list[str] = []
            if self.config.cursor_field:
                modes.append(SyncMode.INCREMENTAL)
                cursor = [self.config.cursor_field]
            streams.append(
                Stream(
                    name=path.stem,
                    json_schema=await asyncio.to_thread(_infer_schema, path, self.config.encoding),
                    supported_sync_modes=modes,
                    source_defined_cursor=bool(cursor),
                    default_cursor_field=cursor,
                )
            )
        return Catalog(streams=streams)

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        by_name = {p.stem: p for p in await asyncio.to_thread(self._files)}
        for configured in catalog.streams:
            name = configured.stream.name
            path = by_name.get(name)
            if path is None:
                continue
            cursor = incremental_cursor(configured)
            tracker = CursorTracker(name, state, enabled=cursor is not None)
            # File I/O and JSON parsing happen in a worker thread, a chunk of rows per hop.
            async for data in iterate_in_thread(_rows(path, self.config.encoding)):
                if cursor:
                    value = data.get(cursor)
                    if value is None or not is_newer(value, tracker.start):
                        continue
                    tracker.observe(value)
                yield Record(stream=name, data=data)
            if final := tracker.final_state():
                yield final


def _rows(path: Path, encoding: str) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding=encoding) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                yield data


def _infer_schema(path: Path, encoding: str, sample: int = 50) -> dict[str, Any]:
    """Very small JSON Schema inference from the first ``sample`` rows."""
    props: dict[str, Any] = {}
    with path.open("r", encoding=encoding) as fh:
        for i, line in enumerate(fh):
            if i >= sample:
                break
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                add_properties(props, row)
    return {"type": "object", "properties": props}
