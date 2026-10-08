"""Domain exceptions.

Services and domain modules raise these; only routes translate them to HTTP
statuses. Never raise ``HTTPException`` below the route layer.

Definitions live in the shared error_contract package. This module preserves
existing import paths while callers migrate.
"""

from __future__ import annotations

from error_contract import (
    ApplicationError,
    BadRequestError,
    ConflictError,
    DependencyResponseError,
    DependencyUnavailableError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
    ValidationFailedError,
    from_httpx_error,
)
from error_contract.domain import (
    DuplicateComponentError,
    FlowBuildError,
    FlowError,
    FlowNotPublishedError,
    FlowValidationError,
    FlowVersionConflictError,
    MissingMigrationError,
    NotAResourceNodeError,
    UnknownComponentError,
    UnknownOptionsSourceError,
)


class LiveSyncJobConflictError(Exception):
    """A write would give a datasource a second pending or running sync job.

    ``connector_sync_jobs`` admits one live job per datasource. This is raised
    when a job that was closed in the meantime is written as live again: a
    sibling worker declared it dead and started the datasource anew.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"sync job {job_id} cannot be live: its datasource already has a pending or running job")


__all__ = [
    "ApplicationError",
    "BadRequestError",
    "ConflictError",
    "DependencyResponseError",
    "DependencyUnavailableError",
    "DuplicateComponentError",
    "FlowBuildError",
    "FlowError",
    "FlowNotPublishedError",
    "FlowValidationError",
    "FlowVersionConflictError",
    "ForbiddenError",
    "LiveSyncJobConflictError",
    "MissingMigrationError",
    "NotAResourceNodeError",
    "NotFoundError",
    "RateLimitedError",
    "UnauthorizedError",
    "UnknownComponentError",
    "UnknownOptionsSourceError",
    "ValidationFailedError",
    "from_httpx_error",
]
