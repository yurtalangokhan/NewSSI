"""Native health/readiness transport, excluded from application responses."""

from error_contract import DependencyUnavailableError
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.controller.health_controller import get_health_controller

router = APIRouter(tags=["health"])


@router.get("", include_in_schema=False)
@router.get("/")
async def health_check():
    return await get_health_controller().health()


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    try:
        payload = await get_health_controller().readiness()
        return JSONResponse(content=payload)
    except DependencyUnavailableError as error:
        return JSONResponse(status_code=error.status_code, content=error.details["readiness"])
