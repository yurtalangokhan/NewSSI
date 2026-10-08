"""The console destination: records to stdout.

Containers already collect stdout, so this is the destination that needs no
collector, no volume, and no configuration. It is the default.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

from . import LogSink

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..formatter import BaseFormatter


class ConsoleSink(LogSink):
    """Write records to a stream, stdout unless configured otherwise."""

    def __init__(self, *, formatter: BaseFormatter, options: dict[str, Any] | None = None) -> None:
        super().__init__()
        options = options or {}
        self.setFormatter(formatter)
        self.setLevel(_level_of(options.get("level")))
        stream = str(options.get("stream", "stdout")).lower()
        self.stream = sys.stderr if stream == "stderr" else sys.stdout

    def emit(self, record: logging.LogRecord) -> None:
        """Write one record to the stream.

        Nothing is raised on failure: a broken stream must not take down the
        request that was trying to log.
        """
        try:
            self.stream.write(self.format(record) + "\n")
            self.flush()
        except Exception:  # noqa: BLE001 - a logging failure must never propagate
            self.handleError(record)


def _level_of(name: str | None) -> int:
    """Resolve a configured level name, treating an unknown name as notset."""
    if not name:
        return logging.NOTSET
    return getattr(logging, str(name).upper(), logging.NOTSET)


def build_console_sink(*, formatter: BaseFormatter, options: dict[str, Any]) -> ConsoleSink:
    """Build the console destination from configuration options."""
    return ConsoleSink(formatter=formatter, options=options)
