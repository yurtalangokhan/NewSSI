"""Compatibility re-exports for the shared identity error contract."""

from error_contract.identity import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    UnauthorizedError,
    UserServiceError,
)

__all__ = [
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "InternalServerError",
    "NotFoundError",
    "UnauthorizedError",
    "UserServiceError",
]
