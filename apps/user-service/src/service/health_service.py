"""Readiness dependency checks, independent of HTTP transport."""

from error_contract import ApplicationError, DependencyUnavailableError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.database.engine import get_db_engine
from src.core.observability import (
    DependencyPolicy,
    DependencyStatus,
    dependency_registry,
    readiness_payload,
)


class HealthService:
    def health(self) -> dict:
        return {"status": "healthy", "service": "user-service"}

    async def readiness(self) -> dict:
        try:
            async with get_db_engine().connect() as connection:
                await connection.execute(select(1))
            dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
        except (SQLAlchemyError, OSError, TimeoutError, ApplicationError):
            dependency_registry.record(
                DependencyStatus(
                    name="postgres",
                    policy=DependencyPolicy.REQUIRED,
                    status="failed",
                )
            )
        payload = readiness_payload(service_name="user-service")
        if payload["status"] != "ready":
            raise DependencyUnavailableError(details={"readiness": payload})
        return payload
