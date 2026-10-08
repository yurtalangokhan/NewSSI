"""Exception hierarchy for the connector framework.

Every error the package raises on purpose derives from :class:`ConnectorError`,
so callers can catch a single base type at service boundaries. Errors of the
libraries underneath (``httpx``, database drivers) are not wrapped: they pass
through as they are.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class ConnectorError(Exception):
    """Base class for all connector framework errors."""


class ConnectorNotFoundError(ConnectorError):
    """Requested connector name is not registered."""

    def __init__(self, name: str, kind: str = "connector") -> None:
        self.name = name
        self.kind = kind
        super().__init__(f"{kind} '{name}' is not registered")


class ConnectorDisabledError(ConnectorError):
    """Connector exists but is hidden by the active visibility policy."""

    def __init__(self, name: str, reason: str | None = None) -> None:
        self.name = name
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"connector '{name}' is disabled{detail}")


class DuplicateConnectorError(ConnectorError):
    """A connector with the same name is already registered."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"connector '{name}' is already registered")


class MissingExtraError(ConnectorError, ImportError):
    """An optional dependency is not installed.

    Also an ``ImportError``, which is what it is to code that does not know
    this package.
    """

    def __init__(self, feature: str, extra: str) -> None:
        self.feature = feature
        self.extra = extra
        super().__init__(
            f"{feature} requires the '{extra}' extra: pip install connector-py[{extra}]"
        )


class ConfigValidationError(ConnectorError):
    """Connector configuration does not satisfy its specification.

    ``errors`` holds one ``{"type", "loc", "msg"}`` entry per problem. Submitted
    values are never part of it or of the message: they may be secrets, and the
    message ends up in logs and job records.
    """

    def __init__(self, name: str, errors: Sequence[Mapping[str, Any]]) -> None:
        self.name = name
        self.errors: list[dict[str, Any]] = [dict(error) for error in errors]
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error.get('loc') or ()) or 'config'}: "
            f"{error.get('msg', 'invalid')}"
            for error in self.errors
        )
        super().__init__(f"invalid configuration for connector '{name}': {problems}")


class CheckFailedError(ConnectorError):
    """Connectivity check against the external system failed."""


class StreamNotFoundError(ConnectorError):
    """A requested stream is not present in the discovered catalog."""

    def __init__(self, stream: str) -> None:
        self.stream = stream
        super().__init__(f"stream '{stream}' not found in catalog")


class SourceError(ConnectorError):
    """The external system answered, but not with what a sync can use.

    A rejected token request, an application-level error in a ``200`` response,
    a protocol command that failed. Transport failures stay the library's own
    exceptions.
    """


class DestinationWriteError(ConnectorError):
    """A batch could not be persisted.

    The runner raises it after the last retry. A destination that raises it
    itself says "retrying this batch is pointless"; the runner then gives up at
    once.
    """


class SyncError(ConnectorError):
    """A sync job could not be started or tracked."""


class SyncAlreadyRunningError(SyncError):
    """The connection already has a live job, in this process or on a sibling."""

    def __init__(
        self, connection_id: str, job_id: str | None = None, worker_id: str | None = None
    ) -> None:
        self.connection_id = connection_id
        self.job_id = job_id
        self.worker_id = worker_id
        owner = f"job '{job_id}'" if job_id else "another worker"
        if job_id and worker_id:
            owner += f" on worker '{worker_id}'"
        super().__init__(f"connection '{connection_id}' is already being synced by {owner}")


class JobNotFoundError(SyncError):
    """No job with this id is known to the runner or its job store."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"job {job_id} not found")


class JobTakenOverError(SyncError):
    """The job store refused to make a job live again: another worker ended it.

    Raised by a job store when a non-terminal status is written over a terminal
    one. The runner that receives it stops executing the job; the connection
    belongs to whoever declared it dead.
    """

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"job {job_id} was ended by another worker and cannot be made live again")
