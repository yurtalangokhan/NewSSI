"""Validate user-service response data at this service's client boundary."""

from typing import Any

from error_contract import ApplicationError, DependencyResponseError
import httpx
from pydantic import ValidationError

from src.shared.response_models import ResponseModel


def read_user_response(response: httpx.Response) -> Any:
    try:
        payload = response.json()
        if not isinstance(payload, dict) or not {"statusCode", "message", "data", "error"} <= payload.keys():
            raise DependencyResponseError()
        result = ResponseModel[Any].model_validate(payload, strict=True)
    except (ValueError, ValidationError) as exc:
        raise DependencyResponseError() from exc
    if result.statusCode != response.status_code:
        raise DependencyResponseError()
    if result.error is not None and 400 <= result.statusCode <= 599:
        raise ApplicationError(
            status_code=result.statusCode,
            code=result.error.code,
            message=result.error.message,
            message_key=None,
        )
    if not 200 <= result.statusCode < 300 or result.error is not None:
        raise DependencyResponseError()
    return result.data
