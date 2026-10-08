"""Logging configuration as data.

:class:`LoggerConfig` is the complete description of how a service logs: which
service it is, how verbose, in which format, and to which destinations. It
reads no environment and imports no configuration module, so the package stays
free of service knowledge and a test can build one without patching anything.

A service's ``core/observability`` binding owns the mapping from its own
environment names onto this object. That mapping is the only service-specific
part; everything after it is shared.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class LogFormat(StrEnum):
    """Output format shared by every destination."""

    TEXT = "text"
    JSON = "json"


class UnknownSinkError(ValueError):
    """A configuration named a destination that no sink is registered for.

    This is raised at startup rather than at first log write, so a typo in a
    deployment's configuration is reported while the process is still starting
    and someone is watching, not silently at 3 a.m. when the first record is
    dropped.
    """


@dataclass(frozen=True)
class SinkConfig:
    """One destination and its options.

    Options are passed to the sink's constructor. They are kept as an opaque
    mapping so a new sink can take options the package knows nothing about,
    which is what lets a target-specific sink be added without changing this
    module.
    """

    name: str
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # frozenset + MappingProxyType keep the frozen dataclass honest: a caller
        # cannot mutate the options after the configuration is built.
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


@dataclass(frozen=True)
class LoggerConfig:
    """Everything a service needs to say about its own logging."""

    service_name: str
    level: str = "INFO"
    format: LogFormat = LogFormat.TEXT
    sinks: tuple[SinkConfig, ...] = (SinkConfig(name="console"),)
    correlation_header: str = "x-request-id"
    quiet_loggers: tuple[str, ...] = ()
    include_source: bool = True

    def __post_init__(self) -> None:
        if not self.service_name:
            raise ValueError("service_name is required: every record carries it")
        object.__setattr__(self, "level", self.level.upper())
        # Configuration values arrive from an env file and from callers that were
        # written against the older case-insensitive comparison, so the format
        # name is normalised here rather than at each read site.
        object.__setattr__(self, "format", LogFormat(str(self.format).strip().lower()))
        object.__setattr__(self, "sinks", tuple(self.sinks))
        object.__setattr__(self, "quiet_loggers", tuple(self.quiet_loggers))
        if not self.sinks:
            raise ValueError(
                "at least one sink is required; a service with no destination logs nothing"
            )

    @property
    def sink_names(self) -> tuple[str, ...]:
        """The configured destination names, in configuration order."""
        return tuple(sink.name for sink in self.sinks)

    def is_json(self) -> bool:
        """Whether records render as JSON rather than text."""
        return self.format is LogFormat.JSON


#: The destinations a deployment selects by name, and the options each one reads.
#: Shared so the four services cannot drift into four different interpretations of
#: the same setting.
_SINK_OPTION_KEYS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "console": ("stream", "level"),
        "file": ("path", "max_bytes", "backup_count", "level"),
        "syslog": ("address", "facility", "level"),
        "external": (
            "url",
            "batch_size",
            "flush_interval",
            "max_queue",
            "max_retries",
            "retry_backoff",
            "shutdown_timeout",
            "headers",
        ),
        "elasticsearch": (
            "url",
            "index",
            "batch_size",
            "flush_interval",
            "max_queue",
            "max_retries",
            "retry_backoff",
            "shutdown_timeout",
            "headers",
        ),
    }
)


def sink_for(output: str, **options: Any) -> SinkConfig:
    """Return the destination named by *output* with its own options selected.

    Only the options the named destination knows are passed on, so a deployment
    that sets every logging variable does not hand ``path`` to a syslog sink.
    """
    name = str(output).strip().lower()
    accepted = _SINK_OPTION_KEYS.get(name)
    if accepted is None:
        raise UnknownSinkError(
            f"unknown log sink {name!r}; configured sinks: {', '.join(sorted(_SINK_OPTION_KEYS))}"
        )
    supplied = {
        key: value
        for key, value in options.items()
        if key in accepted and value is not None
    }
    return SinkConfig(name=name, options=supplied)


def build_logger_config(
    service_name: str,
    *,
    level: str = "INFO",
    format: str = LogFormat.TEXT,
    output: str = "console",
    file_path: str | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
    include_source: bool = True,
    quiet_loggers: tuple[str, ...] = (),
    syslog_address: str | None = None,
    syslog_facility: str | None = None,
    external_url: str | None = None,
    external_bearer_token: str | None = None,
    external_batch_size: int | None = None,
    external_flush_interval: float | None = None,
    external_max_queue: int | None = None,
    external_max_retries: int | None = None,
    external_retry_backoff: float | None = None,
    external_shutdown_timeout: float | None = None,
    elasticsearch_index: str | None = None,
) -> LoggerConfig:
    """Assemble a :class:`LoggerConfig` from plain values.

    This is where a deployment's settings stop being separate variables and
    become one description of the service's logging. It takes values rather than
    reading the environment, so the package stays free of configuration
    knowledge and this function is directly testable; a service binding supplies
    the values from its own environment names.
    """
    return LoggerConfig(
        service_name=service_name,
        level=level,
        format=LogFormat(str(format).strip().lower()),
        sinks=(
            sink_for(
                output,
                stream="stdout",
                path=file_path,
                max_bytes=max_bytes,
                backup_count=backup_count,
                address=_split_address(syslog_address),
                facility=syslog_facility,
                url=external_url,
                headers={"Authorization": f"Bearer {external_bearer_token}"}
                if external_bearer_token
                else None,
                batch_size=external_batch_size,
                flush_interval=external_flush_interval,
                max_queue=external_max_queue,
                max_retries=external_max_retries,
                retry_backoff=external_retry_backoff,
                shutdown_timeout=external_shutdown_timeout,
                index=elasticsearch_index,
            ),
        ),
        quiet_loggers=quiet_loggers,
        include_source=include_source,
    )


def _split_address(address: str | None) -> tuple[str, int] | None:
    """Read a ``host:port`` destination address."""
    if not address:
        return None
    host, separator, port = address.rpartition(":")
    if not separator:
        return (address, 514)
    return (host, int(port))
