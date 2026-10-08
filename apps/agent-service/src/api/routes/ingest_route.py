"""
Ingestion Routes.

Datasource records are ingested in-process by the connector runtime, so there
is no batch endpoint here. What remains is the live source preview used by the
documents tab.
"""

from __future__ import annotations

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import (
    AuthenticatedUser,
    require_permission,
    require_user_or_internal_service_token,
)
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.ingest import SourcePreviewRequest, SourcePreviewResponse
from service.datasources import datasource_application_service

logger = get_logger(__name__)

router = APIRouter(
    tags=["ingestion"],
    dependencies=[Depends(require_user_or_internal_service_token)],
)


# ============================================================================
# Source Preview Endpoint (live query from original source)
# ============================================================================


@router.post("/source-preview", response_model=ResponseModel[SourcePreviewResponse])
async def source_preview(
    request: Request,
    response: Response,
    req: SourcePreviewRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:update"))],
) -> ResponseModel[Any]:
    """Describe the streams the datasource's connector can read right now.

    This connects to the source with the datasource's stored credentials, so
    it takes the permission that editing the connection takes.
    """
    try:
        return ResponseModel(data=await datasource_application_service.source_preview(datasource_id=req.datasource_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
