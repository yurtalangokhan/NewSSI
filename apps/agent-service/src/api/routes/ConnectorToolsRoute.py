"""Connector options and internal-only credential resolution."""

import asyncio
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from i18n import t

from api.dependencies import AuthenticatedUser, require_permission
from controller.connector_tool_controller import get_connector_tool_controller
from core.settings import settings
from models.connector_tools import ConnectorResolveRequest

router = APIRouter(tags=["connector-tools"])
RESOLUTION_TIMEOUT_SECONDS = 15


def _internal_identity(request: Request) -> str:
    expected = (settings.INTERNAL_SERVICE_TOKEN or "").strip()
    supplied = request.headers.get("x-internal-service-token", "")
    user_id = request.headers.get("x-user-id", "").strip()
    if (
        not expected
        or not secrets.compare_digest(expected, supplied)
        or not user_id
        or user_id == "internal-service"
    ):
        raise HTTPException(
            403,
            detail=t(
                "connectors.internal_required", default="Trusted internal identity is required."
            ),
        )
    return user_id


@router.get("/datasources/tool-options")
async def connector_options(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
) -> list[dict]:
    return await get_connector_tool_controller().list_options()


@router.post("/internal/connector-tools/resolve")
async def resolve_connector(
    body: ConnectorResolveRequest,
    response: Response,
    user_id: Annotated[str, Depends(_internal_identity)],
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with asyncio.timeout(RESOLUTION_TIMEOUT_SECONDS):
            return await get_connector_tool_controller().resolve(
                body.persona_id, str(body.datasource_id), body.operation, user_id
            )
    except TimeoutError:
        raise HTTPException(
            504,
            detail=t("connectors.timeout", default="Connector resolution timed out."),
            headers={"Cache-Control": "no-store"},
        ) from None
