"""Log destinations: the extension point for any output, local or remote.

A sink is a :class:`logging.Handler`, so everything the standard library offers
keeps working, and every destination is reached the same way. What this module
adds is a lifecycle and a registry.

The lifecycle is explicit because a remote destination has work that a stream
handler does not: connecting, batching, draining. ``startup`` opens it, ``emit``
accepts a record, ``flush`` drains what is pending, and ``shutdown`` stops the
worker within a bounded time.

Registering a sink by name is what makes an external platform a configuration
change rather than a code change. A target-specific sink subclasses
:class:`~observability.sinks.external.ExternalSink`, implements one method, and
a deployment selects it by name.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from ..config import SinkConfig
    from ..formatter import BaseFormatter

SinkBuilder = Callable[..., logging.Handler]


class LogSink(logging.Handler):
    """Base class for every destination.

    Subclasses set their own level and formatter; the manager hands every sink
    the *same* formatter instance, which is what makes two destinations agree on
    the rendered record by construction.
    """

    def startup(self) -> None:
        """Open whatever resource the destination needs.

        Called once, before the first record. A sink with nothing to open does
        not override this.
        """

    def fields_for(self, record: logging.LogRecord) -> dict[str, Any]:
        """Return the record's contract fields, delegated to the formatter.

        A destination that ships a payload rather than a line needs the fields,
        not the rendering, and must not have to know which formatter class it was
        given. A formatter that is not one of this package's formatters has no
        field set of its own, so its rendered line is carried as the message.
        """
        formatter = self.formatter
        if formatter is None:
            return {"message": record.getMessage()}
        fields_for = getattr(formatter, "fields_for", None)
        if fields_for is None:
            return {"message": formatter.format(record)}
        return fields_for(record)

    def flush(self) -> None:
        """Deliver everything already accepted.

        The default delegates to the standard library, which is correct for the
        synchronous destinations. A destination with a queue overrides it.
        """
        super().flush()

    def shutdown(self) -> None:
        """Stop the destination and release its resources.

        Called once, after the last flush. Must not raise: it runs during
        interpreter and process teardown.
        """
        self.flush()
        super().close()

    def describe(self) -> str:
        """Return a short human description, used in startup logging."""
        return type(self).__name__


_SINKS: dict[str, SinkBuilder] = {}


def register_sink(name: str, builder: SinkBuilder) -> None:
    """Register a destination under *name* so configuration can select it."""
    _SINKS[name] = builder


def available_sinks() -> tuple[str, ...]:
    """Return the registered destination names, sorted."""
    return tuple(sorted(_SINKS))


def create_sink(
    config: SinkConfig,
    *,
    formatter: BaseFormatter,
) -> LogSink:
    """Build the destination named by *config*.

    Raises :class:`~observability.config.UnknownSinkError` for a name nothing is
    registered under, so a misconfigured deployment fails at startup with a
    readable message instead of silently discarding every record.
    """
    builder = _SINKS.get(config.name)
    if builder is None:
        from ..config import UnknownSinkError

        known = ", ".join(available_sinks()) or "none"
        raise UnknownSinkError(
            f"unknown log sink {config.name!r}; registered sinks: {known}"
        )
    return builder(formatter=formatter, options=dict(config.options))


def _register_builtin_sinks() -> None:
    """Register the destinations that ship with the package."""
    from .console import build_console_sink
    from .elasticsearch import build_elasticsearch_sink
    from .external import build_external_sink
    from .file import build_file_sink
    from .syslog import build_syslog_sink

    register_sink("console", build_console_sink)
    register_sink("elasticsearch", build_elasticsearch_sink)
    register_sink("file", build_file_sink)
    register_sink("syslog", build_syslog_sink)
    register_sink("external", build_external_sink)


_register_builtin_sinks()
