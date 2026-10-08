"""The rotating file destination.

Useful when a collector tails a file, and when a process runs outside a
container. Rotation is by size with a fixed backup count, so a long-running
process cannot fill its disk with its own logs.
"""

from __future__ import annotations

import contextlib
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Any

from . import LogSink
from .console import _level_of

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..formatter import BaseFormatter

DEFAULT_PATH = "/var/log/service/app.log"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


class FileSink(LogSink):
    """Write records to a size-rotated file.

    A file that cannot be opened is not fatal: the sink records why and writes
    nothing, and the process keeps running with whatever other destinations are
    configured. A logging destination failing to open must not stop a service
    from serving.
    """

    def __init__(self, *, formatter: BaseFormatter, options: dict[str, Any] | None = None) -> None:
        super().__init__()
        options = options or {}
        self.setFormatter(formatter)
        self.setLevel(_level_of(options.get("level")))
        self.path = str(options.get("path", DEFAULT_PATH))
        self.max_bytes = int(options.get("max_bytes", DEFAULT_MAX_BYTES))
        self.backup_count = int(options.get("backup_count", DEFAULT_BACKUP_COUNT))
        self._handler: logging.Handler | None = None
        self.disabled_reason: str | None = None

    def startup(self) -> None:
        """Open the file, creating its directory, and record why on failure."""
        directory = os.path.dirname(self.path)
        if directory and not os.path.exists(directory):
            with contextlib.suppress(OSError):
                os.makedirs(directory, exist_ok=True)
        try:
            handler = RotatingFileHandler(
                self.path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
            )
        except OSError as exc:
            self.disabled_reason = f"cannot open {self.path}: {exc}"
            return
        handler.setFormatter(self.formatter)
        handler.setLevel(self.level)
        self._handler = handler

    def emit(self, record: logging.LogRecord) -> None:
        """Write one record through the rotating handler."""
        if self._handler is None:
            return
        try:
            self._handler.emit(record)
        except Exception:  # noqa: BLE001 - a logging failure must never propagate
            self.handleError(record)

    def flush(self) -> None:
        """Flush the underlying file."""
        if self._handler is not None:
            self._handler.flush()

    def shutdown(self) -> None:
        """Close the file."""
        if self._handler is not None:
            self._handler.close()
            self._handler = None

    def describe(self) -> str:
        """Describe the destination, including why it is not writing."""
        if self._handler is None:
            return f"FileSink(not writing: {self.disabled_reason})"
        return f"FileSink({self.path})"


def build_file_sink(*, formatter: BaseFormatter, options: dict[str, Any]) -> FileSink:
    """Build the rotating file destination from configuration options."""
    return FileSink(formatter=formatter, options=options)
