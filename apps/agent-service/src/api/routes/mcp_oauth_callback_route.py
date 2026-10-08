"""Browser-facing OAuth callback for external MCP servers.

``POST /api/mcp/oauth/callback?code=&state=`` — not under ``/admin``: any
authenticated user completes their own per-user authorization. ``state`` is
authoritative; a legacy JSON body (``{code, state, ...}``) is also accepted.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.mcp_admin import OAuthCallbackResponse
from service.mcp.mcp_oauth_callback_application_service import MCPOAuthCallbackApplicationService
from service.mcp.mcp_oauth_service import MCPOAuthService

logger = get_logger(__name__)
router = APIRouter(tags=["mcp-oauth"])


def _oauth_service() -> MCPOAuthService:
    return MCPOAuthService.get_instance()


@router.post("/api/mcp/oauth/callback", response_model=ResponseModel[OAuthCallbackResponse])
async def mcp_oauth_callback(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    code: str | None = None,
    state: str | None = None,
) -> ResponseModel[Any]:
    if not code or not state:
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        if not isinstance(body, dict):
            body = {}
        code = code or body.get("code")
        state = state or body.get("state")
    try:
        return ResponseModel(
            data=await MCPOAuthCallbackApplicationService(oauth_service=_oauth_service).mcp_oauth_callback(
                user=user, code=code, state=state
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
