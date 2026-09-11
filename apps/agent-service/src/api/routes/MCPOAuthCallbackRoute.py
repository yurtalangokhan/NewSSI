"""Browser-facing OAuth callback for external MCP servers.

``POST /api/mcp/oauth/callback?code=&state=`` — not under ``/admin``: any
authenticated user completes their own per-user authorization. ``state`` is
authoritative; a legacy JSON body (``{code, state, ...}``) is also accepted.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import AuthenticatedUser, require_user
from core.logger import get_logger
from service.MCPCredentialService import MCPAuthError
from service.MCPOAuthService import MCPOAuthService

logger = get_logger(__name__)

router = APIRouter(tags=["mcp-oauth"])


def _oauth_service() -> MCPOAuthService:
    return MCPOAuthService.get_instance()


@router.post("/api/mcp/oauth/callback")
async def mcp_oauth_callback(
    request: Request,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
    code: str | None = None,
    state: str | None = None,
) -> dict[str, str]:
    if not code or not state:
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        code = code or body.get("code")
        state = state or body.get("state")

    if not code or not state:
        raise HTTPException(status_code=400, detail="invalid oauth callback: missing code or state")

    try:
        return await _oauth_service().complete(state, code)
    except MCPAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
