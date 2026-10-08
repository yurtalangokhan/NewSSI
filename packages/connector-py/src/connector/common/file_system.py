"""File-tree sources: one reader, many transports.

FTP, SFTP, SMB shares and local directories differ only in *how a folder is
listed and a file is opened*. That part is the small blocking
:class:`RemoteFileSystem` protocol; everything else (walking, glob selection,
format parsing, binary metadata, the modification-time cursor) lives once in
:class:`FileSystemSource`.

The transports are blocking libraries (``ftplib``, ``paramiko``, ``smbclient``),
so all calls into a file system run in a worker thread.

Stream ``files``:

* ``csv`` / ``jsonl`` / ``json`` yield one record per row,
* text-like files yield one record with ``content``,
* anything else yields a metadata record with ``binary: true`` so a document
  pipeline can fetch and parse it (this package has no PDF/Office parsers).
"""

from __future__ import annotations

import asyncio
import io
import mimetypes
import os
import posixpath
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol, TypeVar

from pydantic import BaseModel, Field

from ..base import BaseSource
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)
from .cursor import CursorTracker, ReadAtCursor
from .file_formats import CHECKPOINT_FILES, EXT_TO_FORMAT, glob_match, parse_records

ConfigT = TypeVar("ConfigT", bound="FileSelectionOptions")


@dataclass(frozen=True)
class FileEntry:
    path: str
    """Absolute path on the file system, ``/`` separated."""
    size: int = 0
    modified: datetime | None = None
    is_dir: bool = False

    @property
    def name(self) -> str:
        return posixpath.basename(self.path.rstrip("/"))


class RemoteFileSystem(Protocol):
    """Blocking transport. Implementations need not be thread-safe: calls are serialized."""

    def list_dir(self, path: str) -> list[FileEntry]: ...

    def read_bytes(self, path: str) -> bytes: ...

    def close(self) -> None: ...


FileSystemFactory = Callable[[Any], RemoteFileSystem]


class FileSelectionOptions(BaseModel):
    """Which files to read and how to parse them; shared by every file-tree source."""

    glob: str = Field(default="**/*", description="Pattern relative to each root path.")
    recursive: bool = True
    include_binary_metadata: bool = Field(
        default=True, description="Emit a metadata record for files that are not parsed here."
    )
    max_file_size_bytes: int | None = Field(default=50_000_000, description="Skip larger files.")
    max_files: int | None = Field(
        default=None,
        description="Safety cap per sync: at most this many files are read, oldest first. "
        "An incremental sync counts only the files it has not read yet.",
    )
    encoding: str = "utf-8"
    csv_delimiter: str = Field(
        default=",",
        description="Column delimiter of csv files. A '.tsv' file is split on tabs unless "
        "this is changed.",
    )


class LocalFileSystem:
    """Directories of this machine (uploads folder, NFS / CIFS mount points)."""

    def list_dir(self, path: str) -> list[FileEntry]:
        entries = []
        with os.scandir(path) as it:
            for item in it:
                stat = item.stat()
                entries.append(
                    FileEntry(
                        path=item.path.replace("\\", "/"),
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        is_dir=item.is_dir(),
                    )
                )
        return entries

    def read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as fh:
            return fh.read()

    def close(self) -> None:
        return None


class FileSystemSource(BaseSource[ConfigT]):
    """Base class. Subclasses provide :meth:`roots`, :meth:`open_file_system`, :meth:`uri_for`."""

    stream_name: ClassVar[str] = "files"

    def __init__(self, config: ConfigT, fs_factory: FileSystemFactory | None = None) -> None:
        super().__init__(config)
        self._fs_factory = fs_factory

    # ---- to implement ---------------------------------------------------------------

    def roots(self) -> list[str]:
        raise NotImplementedError

    def open_file_system(self) -> RemoteFileSystem:
        raise NotImplementedError

    def uri_for(self, path: str) -> str:
        return path

    def binary_extra(self, entry: FileEntry) -> dict[str, Any]:
        """Additional fields for metadata-only records."""
        return {}

    # ---- connector API --------------------------------------------------------------

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def _open(self) -> RemoteFileSystem:
        return self._fs_factory(self.config) if self._fs_factory else self.open_file_system()

    async def check(self) -> CheckResult:
        def _sync() -> None:
            fs = self._open()
            try:
                for root in self.roots():
                    fs.list_dir(root)
            finally:
                fs.close()

        try:
            await asyncio.to_thread(_sync)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=f"{type(exc).__name__}: {exc}")
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name=self.stream_name,
                    json_schema={
                        "type": "object",
                        "properties": {
                            "_source_file": {"type": "string"},
                            "_source_uri": {"type": "string"},
                            "_source_file_last_modified": {"type": "string", "format": "date-time"},
                            "content": {"type": "string"},
                            "binary": {"type": "boolean"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["_source_file_last_modified"],
                )
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        configured = next((s for s in catalog.streams if s.stream.name == self.stream_name), None)
        if configured is None:
            return
        # Files are read oldest first, so the position can be saved between them.
        tracker = CursorTracker(
            self.stream_name,
            state,
            enabled=configured.sync_mode is SyncMode.INCREMENTAL,
            ordered=True,
            checkpoint_every=CHECKPOINT_FILES,
        )
        read_at = ReadAtCursor(tracker, state.get(self.stream_name) if state else None)

        fs = await asyncio.to_thread(self._open)
        try:
            files = await asyncio.to_thread(self._walk, fs)
            for root, entry in self._due(files, read_at):
                relative = posixpath.relpath(entry.path, root) if entry.path != root else entry.name
                stamp = entry.modified.isoformat() if entry.modified else None
                meta = {
                    "_source_file": relative,
                    "_source_uri": self.uri_for(entry.path),
                    "_source_file_last_modified": stamp,
                }
                checkpoint = tracker.observe(stamp)
                if checkpoint:
                    yield read_at.attach(checkpoint)
                if stamp is not None:
                    read_at.note(stamp, entry.path)
                for row in await asyncio.to_thread(self._rows, fs, entry):
                    yield Record(stream=self.stream_name, data={**row, **meta})
        finally:
            await asyncio.to_thread(fs.close)
        if final := tracker.final_state():
            yield read_at.attach(final)

    # ---- blocking helpers (run in a thread) ----------------------------------------------

    def _walk(self, fs: RemoteFileSystem) -> list[tuple[str, FileEntry]]:
        cfg = self.config
        found: list[tuple[str, FileEntry]] = []
        for root in self.roots():
            root = root.rstrip("/") or "/"
            queue: deque[str] = deque([root])
            seen = {root}
            while queue:
                folder = queue.popleft()
                for entry in fs.list_dir(folder):
                    if entry.is_dir:
                        if cfg.recursive and entry.path not in seen:
                            seen.add(entry.path)
                            queue.append(entry.path)
                        continue
                    if not glob_match(posixpath.relpath(entry.path, root), cfg.glob):
                        continue
                    if cfg.max_file_size_bytes is not None and entry.size > cfg.max_file_size_bytes:
                        continue
                    found.append((root, entry))
        epoch = datetime.fromtimestamp(0, tz=UTC)
        found.sort(key=lambda item: (item[1].modified or epoch, item[1].path))
        return found

    def _due(
        self, files: list[tuple[str, FileEntry]], read_at: ReadAtCursor
    ) -> list[tuple[str, FileEntry]]:
        """What this sync reads: the files not yet read, ``max_files`` of them at most.

        The cap applies to what is left to read. Applied to the whole listing, it
        would be used up by the oldest files on every run and an incremental sync
        would never get past them. The cut does not fall between files with the
        same modification time either: that time becomes the cursor, and the ones
        left behind would look read.
        """
        due = [(root, entry) for root, entry in files if read_at.due(entry.modified, entry.path)]
        cap = self.config.max_files
        if not cap or len(due) <= cap:
            return due
        edge = due[cap - 1][1].modified
        while cap < len(due) and due[cap][1].modified == edge:
            cap += 1
        return due[:cap]

    def _rows(self, fs: RemoteFileSystem, entry: FileEntry) -> list[dict[str, Any]]:
        fmt = EXT_TO_FORMAT.get(posixpath.splitext(entry.path)[1].lower())
        if fmt is None:
            if not self.config.include_binary_metadata:
                return []
            return [
                {
                    "binary": True,
                    "file_name": entry.name,
                    "mime_type": mimetypes.guess_type(entry.name)[0],
                    "size": entry.size,
                    **self.binary_extra(entry),
                }
            ]
        data = fs.read_bytes(entry.path)
        return list(
            parse_records(
                io.BytesIO(data),
                fmt,
                encoding=self.config.encoding,
                csv_delimiter=self.config.csv_delimiter,
                name=entry.name,
            )
        )
