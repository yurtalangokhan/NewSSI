"""The single entry point a service uses to configure and obtain logging.

Everything a service does with logging goes through this module: configure once
at startup, then ask for a logger. The service's binding decides *what* the
configuration is; this module decides what happens with it.

The design point that matters is that one formatter instance is built per
configuration and handed to every sink. Two destinations therefore cannot
disagree about the rendered record, because neither of them owns the field list
or the formatter. Adding a destination does not change what a record looks like.
"""

from __future__ import annotations

import logging
import threading

from .config import LogFormat, LoggerConfig, SinkConfig
from .context import LogContext, request_scope, set_context, set_context_tokens
from .formatter import JsonFormatter, TextFormatter
from .sinks import LogSink, available_sinks, create_sink

# Fallback used when a service obtains a logger before configuring logging, which
# happens when a module is imported during startup. Records still reach stdout
# instead of being dropped by the standard library's last-resort handler.
DEFAULT_CONFIG = LoggerConfig(service_name="unconfigured")

_lock = threading.Lock()
_config: LoggerConfig | None = None
_sinks: tuple[LogSink, ...] = ()


def configure(config: LoggerConfig) -> LoggerConfig:
    """Install *config* as this process's logging configuration.

    Calling this again reconfigures in place: the previous sinks are shut down
    and the root logger's handlers are replaced rather than appended to, so a
    repeated call cannot produce duplicate records. It is safe to call from a
    test and from a service's lifespan.
    """
    global _config, _sinks

    formatter = _build_formatter(config)
    sinks: list[LogSink] = []
    try:
        for sink_config in config.sinks:
            sink = create_sink(sink_config, formatter=formatter)
            sink.setLevel(configured_level(config))
            sink.startup()
            sinks.append(sink)
    except Exception:
        # A destination that fails to start (an unknown name, an unregistered
        # external target) must not leave the ones that did start holding
        # resources; shut them down and let the error reach the caller.
        for started in sinks:
            _shutdown_quietly(started)
        raise

    with _lock:
        previous = _sinks
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for sink in sinks:
            root.addHandler(sink)
        root.setLevel(configured_level(config))
        for logger_name in config.quiet_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
        _config = config
        _sinks = tuple(sinks)

    # Outside the lock: a sink's shutdown may block on a network flush, and
    # holding the lock would serialise every logging call behind it.
    for sink in previous:
        _shutdown_quietly(sink)

    return config


def _build_formatter(config: LoggerConfig) -> JsonFormatter | TextFormatter:
    """Build the one formatter every sink shares."""
    if config.is_json():
        return JsonFormatter(
            service_name=config.service_name,
            include_source=config.include_source,
        )
    return TextFormatter(
        service_name=config.service_name,
        include_source=config.include_source,
    )


def configured_level(config: LoggerConfig) -> int:
    """Resolve a configured level name to its standard library value."""
    return getattr(logging, config.level.upper(), logging.INFO)


def get_logger(name: str, extra_context: dict[str, object] | None = None) -> logging.Logger:
    """Return the logger for *name*.

    This is the call ~170 modules make. It is a thin wrapper over
    :func:`logging.getLogger` so that a service never has to know whether logging
    has been configured yet, and so that the entry point stays in one place if
    that ever changes.
    """
    logger = logging.getLogger(name)
    if extra_context:
        # Per-logger context is attached to the logger itself rather than to each
        # call site, which keeps call sites free of plumbing.
        for key, value in extra_context.items():
            setattr(logger, key, value)
    return logger


def is_configured() -> bool:
    """Whether logging has been configured in this process."""
    return _config is not None


def current_config() -> LoggerConfig | None:
    """Return the active configuration, or ``None`` before configuration."""
    return _config


def active_sinks() -> tuple[LogSink, ...]:
    """Return the installed destinations, for the startup log line."""
    return _sinks


def flush() -> None:
    """Deliver everything the destinations are holding."""
    for sink in _sinks:
        _flush_quietly(sink)


def shutdown() -> None:
    """Flush and close every destination, then clear the configuration."""
    global _config, _sinks
    for sink in _sinks:
        _shutdown_quietly(sink)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    _config = None
    _sinks = ()


def _flush_quietly(sink: LogSink) -> None:
    """Flush a destination without letting a failure reach the caller."""
    try:
        sink.flush()
    except Exception:  # noqa: BLE001 - a logging failure must never propagate
        logging.getLogger(__name__).debug("log sink flush failed", exc_info=True)


def _shutdown_quietly(sink: LogSink) -> None:
    """Shut a destination down without letting a failure reach the caller."""
    try:
        sink.shutdown()
    except Exception:  # noqa: BLE001 - a logging failure must never propagate
        logging.getLogger(__name__).debug("log sink shutdown failed", exc_info=True)


__all__ = [
    "DEFAULT_CONFIG",
    "LogContext",
    "LogFormat",
    "LoggerConfig",
    "SinkConfig",
    "active_sinks",
    "available_sinks",
    "configure",
    "current_config",
    "flush",
    "get_logger",
    "is_configured",
    "request_scope",
    "set_context",
    "set_context_tokens",
    "shutdown",
]
