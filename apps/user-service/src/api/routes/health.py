from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.observability import (
    DependencyPolicy,
    DependencyStatus,
    dependency_registry,
    readiness_payload,
)

router = APIRouter(tags=["health"])


@router.get("", include_in_schema=False)
@router.get("/")
async def health_check():
    return {"status": "healthy", "service": "user-service"}


@router.get("/ready")
async def readiness_check() -> Response:
    try:
        from src.core.database.engine import get_db_engine

        engine = get_db_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
    except Exception:
        dependency_registry.record(
            DependencyStatus(
                name="postgres",
                policy=DependencyPolicy.REQUIRED,
                status="failed",
            )
        )
    payload = readiness_payload(service_name="user-service")
    if payload["status"] != "ready":
        return JSONResponse(status_code=503, content=payload)
    return JSONResponse(content=payload)
