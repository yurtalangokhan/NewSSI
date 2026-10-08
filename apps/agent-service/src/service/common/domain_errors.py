"""Translate unexpected failures of a use case into the platform error contract.

A use case may raise platform errors (``ApplicationError``) on purpose; those pass
through untouched. Everything else is an implementation detail that must not reach
the caller: a ``PermissionError`` becomes a 403, a connection or timeout failure a 503/504
dependency error, and anything unknown is logged once and reported as a generic 500.
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from error_contract import (
    ApplicationError,
    DependencyTimeoutError,
    DependencyUnavailableError,
    ForbiddenError,
    InternalServerError,
)

from core.observability.logger import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def translate_domain_errors(operation: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Decorate an async use case so its failures leave as platform errors."""

    @wraps(operation)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await operation(*args, **kwargs)
        except ApplicationError:
            raise
        except PermissionError as error:
            raise ForbiddenError() from error
        except TimeoutError as error:
            raise DependencyTimeoutError() from error
        except ConnectionError as error:
            raise DependencyUnavailableError() from error
        except Exception as error:
            logger.exception("%s failed", operation.__name__)
            raise InternalServerError() from error

    return wrapper


__all__ = ["translate_domain_errors"]
