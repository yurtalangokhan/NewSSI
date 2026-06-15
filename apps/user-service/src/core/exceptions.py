from typing import Any


class UserServiceError(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(UserServiceError):
    pass


class BadRequestError(UserServiceError):
    pass


class UnauthorizedError(UserServiceError):
    pass


class ForbiddenError(UserServiceError):
    pass


class ConflictError(UserServiceError):
    pass


class InternalServerError(UserServiceError):
    pass
