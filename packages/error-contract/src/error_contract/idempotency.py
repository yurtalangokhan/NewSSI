"""Stable errors for replay and deduplication boundaries."""

from .exceptions import BadRequestError, ConflictError, DependencyUnavailableError


class IdempotencyKeyRequiredError(BadRequestError):
    code = "idempotency_key_required"
    message = "Idempotency-Key header is required for this endpoint."
    message_key = "errors.idempotency_key_required"


class IdempotencyKeyInvalidError(BadRequestError):
    code = "idempotency_key_invalid"
    message = (
        "Idempotency-Key must be 1-255 characters long and contain only "
        "letters, digits, '.', '_' or '-'."
    )
    message_key = "errors.idempotency_key_invalid"


class IdempotencyKeyReusedError(ConflictError):
    code = "idempotency_key_reused"
    message = "Idempotency-Key was already used for a different request or principal."
    message_key = "errors.idempotency_key_reused"


class IdempotencyInProgressError(ConflictError):
    code = "idempotency_request_in_progress"
    message = "A request with this Idempotency-Key is still in progress."
    message_key = "errors.idempotency_request_in_progress"


class IdempotencyStoreUnavailableError(DependencyUnavailableError):
    code = "idempotency_store_unavailable"
    message = (
        "The idempotency store is temporarily unavailable; retry the request "
        "with the same Idempotency-Key."
    )
    message_key = "errors.idempotency_store_unavailable"
