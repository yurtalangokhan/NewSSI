"""Base service class providing common error handling and model conversion patterns."""

from typing import Any, NoReturn

from localization import t

from core.exceptions import (
    ApplicationError,
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
)
from core.observability.logger import get_logger

logger = get_logger(__name__)


class BaseService:
    """Base service providing common patterns.

    Subclasses should:
    - Inject repositories or external clients via constructor
    - Implement domain-specific business logic
    - Raise the domain errors below, never ``HTTPException``

    The helpers raise ``core.exceptions`` errors, which carry a status code and
    a stable machine-readable code but know nothing about HTTP transport. The
    API layer's registered handler renders them, so a service stays callable
    from a worker, a CLI or a test without a request in flight.
    """

    def _raise_not_found(self, detail: str = "common.not_found", **kwargs: Any) -> NoReturn:
        """Raise a 404 domain error. ``detail`` may be a locale key or raw text."""
        raise NotFoundError(message=t(detail, **kwargs), message_key=detail, message_params=kwargs)

    def _raise_bad_request(self, detail: str = "common.bad_request", **kwargs: Any) -> NoReturn:
        """Raise a 400 domain error. ``detail`` may be a locale key or raw text."""
        raise BadRequestError(message=t(detail, **kwargs), message_key=detail, message_params=kwargs)

    def _raise_unauthorized(self, detail: str = "auth.not_authenticated", **kwargs: Any) -> NoReturn:
        """Raise a 401 domain error. ``detail`` may be a locale key or raw text."""
        raise UnauthorizedError(message=t(detail, **kwargs), message_key=detail, message_params=kwargs)

    def _raise_internal_error(self, detail: str = "common.internal_error", **kwargs: Any) -> NoReturn:
        """Raise a 500 domain error, logging *detail* rather than returning it.

        Callers pass anything from a locale key to ``str(exc)`` here, and a 5xx
        body is the one place that must not echo internals back to the caller.
        The resolved text goes to the log, where an operator can correlate it
        with the request id; the client gets the contract's generic message.
        """
        logger.error("Service failed: %s", t(detail, **kwargs))
        raise ApplicationError(status_code=500, code="internal.server_error")

    def _to_dict(self, obj: Any) -> dict[str, Any]:
        """Convert model to dict if it has model_dump."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {"content": str(obj)}
