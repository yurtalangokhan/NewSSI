from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/")
async def health_check():
    return {"status": "healthy", "service": "user-service"}


@router.get("/ready")
async def readiness_check():
    try:
        from src.core.database.engine import get_db_engine

        engine = get_db_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "service": "user-service"}
    except Exception as e:
        return {"status": "not_ready", "service": "user-service", "error": str(e)}
