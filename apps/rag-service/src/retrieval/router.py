# Copyright (c) 2026 Agentic AI Platform
"""HTTP adapter for internal agent-facing retrieval."""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response

from src.retrieval import controller
from src.retrieval.schemas import (
    RetrievalRequestBody,
    RetrievalResponseBody,
)
from src.shared.auth import AuthenticatedUser, require_permission
from src.shared.response_errors import request_locale, set_error_response
from src.shared.response_models import ErrorModel, ResponseModel

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval", response_model=ResponseModel[RetrievalResponseBody])
async def retrieve_knowledge(
    *,
    request: Request,
    response: Response,
    body: RetrievalRequestBody,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:search"))],
):
    """Retrieve bounded vector/graph context for an authorized collection."""
    try:
        result = await controller.retrieve_knowledge(
            body,
            user.identity,
            request.headers.get("x-user-id"),
            request.headers.get("x-tenant-id"),
            user.access_token,
        )
        return ResponseModel(data=RetrievalResponseBody.from_result(result))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
