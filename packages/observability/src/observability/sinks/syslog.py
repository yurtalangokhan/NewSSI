"""The syslog destination: records to the host's logging service.

This is the zero-dependency bridge to an external collector. A container's
logging driver, or a host running rsyslog, already receives what is written
here, so moving from "records in a container log" to "records in a log
platform" can be a configuration change on the collector side with no change to
this package or to any service.
"""

from __future__ import annotations

import logging
import logging.handlers
import socket
from typing import TYPE_CHECKING, Any

from . import LogSink
from .console import _level_of

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..formatter import BaseFormatter

DEFAULT_ADDRESS = ("localhost", 514)
DEFAULT_FACILITY = "user"


class SyslogSink(LogSink):
    """Forward records to a syslog daemon.

    Records are framed by the standard library, so a destination that only
    accepts one line per record cannot be handed a multi-line value. A record
    whose rendered form contains newlines is therefore flattened: the extra
    lines are kept, joined with a literal marker, because dropping them would
    lose the exception detail an operator needs.
    """

    def __init__(self, *, formatter: BaseFormatter, options: dict[str, Any] | None = None) -> None:
        super().__init__()
        options = options or {}
        self.setFormatter(formatter)
        self.setLevel(_level_of(options.get("level")))
        self.address = tuple(options.get("address", DEFAULT_ADDRESS))  # type: ignore[arg-type]
        self.facility = str(options.get("facility", DEFAULT_FACILITY))
        self._handler: logging.Handler | None = None
        self.disabled_reason: str | None = None

    def startup(self) -> None:
        """Open the syslog socket, recording why on failure."""
        socktype = socket.SOCK_DGRAM
        if str(self.address[0]).lower() in ("localhost", "127.0.0.1", "::1"):
            socktype = socket.SOCK_STREAM
        facility = getattr(logging.handlers.SysLogHandler, f"LOG_{self.facility.upper()}", None)
        if facility is None:
            self.disabled_reason = f"unknown syslog facility {self.facility!r}"
            return
        try:
            handler = logging.handlers.SysLogHandler(
                address=self.address,
                facility=facility,
                socktype=socktype,
            )
        except OSError as exc:
            host, port = self.address[0], self.address[1]
            self.disabled_reason = f"cannot reach syslog at {host}:{port}: {exc}"
            return
        handler.setFormatter(self.formatter)
        handler.setLevel(self.level)
        self._handler = handler

    def emit(self, record: logging.LogRecord) -> None:
        """Send one record, flattened to a single frame."""
        if self._handler is None:
            return
        try:
            self._handler.emit(record)
        except Exception:  # noqa: BLE001 - a logging failure must never propagate
            self.handleError(record)

    def format(self, record: logging.LogRecord) -> str:
        """Render the record as one line, since syslog frames are line-based."""
        return self.formatMessage(record).replace("\r", " ").replace("\n", " | ")

    def formatMessage(  # noqa: N802 - the name is fixed by the standard library
        self,
        record: logging.LogRecord,
    ) -> str:
        """Return the formatter's rendering of the record."""
        assert self.formatter is not None  # noqa: S101 - set in __init__
        return self.formatter.format(record)

    def flush(self) -> None:
        """Flush the socket."""
        if self._handler is not None:
            self._handler.flush()

    def shutdown(self) -> None:
        """Close the socket."""
        if self._handler is not None:
            self._handler.close()
            self._handler = None

    def describe(self) -> str:
        """Describe the destination, including why it is not sending."""
        if self._handler is None:
            return f"SyslogSink(not sending: {self.disabled_reason})"
        return f"SyslogSink({self.address[0]}:{self.address[1]})"


def build_syslog_sink(*, formatter: BaseFormatter, options: dict[str, Any]) -> SyslogSink:
    """Build the syslog destination from configuration options."""
    return SyslogSink(formatter=formatter, options=options)
