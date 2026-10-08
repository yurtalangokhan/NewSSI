"""Identity-domain aliases for the shared application error hierarchy."""

from .exceptions import (
    ApplicationError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    UnauthorizedError,
)

UserServiceError = ApplicationError

__all__ = [
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "InternalServerError",
    "NotFoundError",
    "UnauthorizedError",
    "UserServiceError",
]
