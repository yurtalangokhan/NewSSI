"""Internal audit endpoint; historical actor references need no live identity."""

from typing import Annotated, Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Request, Response

from src.api.dependencies import require_auth_or_internal_service_token
from src.controller.audit_controller import get_audit_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.audit import AuditLogRequest

internal_router = APIRouter(prefix="/internal/audit-logs", tags=["audit"])


@internal_router.post("")
async def create_audit_log(
    request: Request,
    response: Response,
    body: Annotated[AuditLogRequest, Body()],
    _authenticated: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    try:
        data = await get_audit_controller().create_log(body)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
