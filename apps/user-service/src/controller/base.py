from collections.abc import Awaitable, Callable
from typing import Any, NoReturn, ParamSpec, TypeVar
import uuid

from error_contract import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)

P = ParamSpec("P")
R = TypeVar("R")


def translate_domain_errors(operation: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Compatibility decorator; typed domain errors must reach the API handler."""
    return operation


class BaseController:
    """Propagate keyed shared errors to the route boundary."""

    @staticmethod
    def parse_user_id(raw: uuid.UUID | str) -> uuid.UUID:
        if isinstance(raw, uuid.UUID):
            return raw
        try:
            return uuid.UUID(raw)
        except (ValueError, TypeError, AttributeError) as exc:
            raise UnauthorizedError() from exc

    def _raise_not_found(self, detail: str = "common.not_found", **kwargs: Any) -> NoReturn:
        raise NotFoundError(message_key=f"errors.user_service.{detail}", message_params=kwargs)

    def _raise_bad_request(self, detail: str = "common.bad_request", **kwargs: Any) -> NoReturn:
        raise BadRequestError(message_key=f"errors.user_service.{detail}", message_params=kwargs)

    def _raise_unauthorized(self, detail: str = "auth.unauthorized", **kwargs: Any) -> NoReturn:
        raise UnauthorizedError(message_key=f"errors.user_service.{detail}", message_params=kwargs)

    def _raise_forbidden(self, detail: str = "auth.forbidden", **kwargs: Any) -> NoReturn:
        raise ForbiddenError(message_key=f"errors.user_service.{detail}", message_params=kwargs)

    def _raise_conflict(self, detail: str = "common.conflict", **kwargs: Any) -> NoReturn:
        raise ConflictError(message_key=f"errors.user_service.{detail}", message_params=kwargs)
