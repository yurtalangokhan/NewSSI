"""
Persona Database Manager.

Facade that delegates to PersonaRepository.
Table creation is managed by Alembic migrations.
"""

from __future__ import annotations

from core.logger import get_logger

logger = get_logger(__name__)
import logging as _stdlib_logging

logger_stdlib = _stdlib_logging.getLogger(__name__)
from typing import Any

from core.db.repositories.persona_repo import PersonaRepository

logger = get_logger(__name__)


class PersonaDB:
    """Facade for persona/agent operations.

    Delegates all database access to PersonaRepository.
    ensure_table() is a no-op — table creation is managed by Alembic migrations.
    """

    _repository = PersonaRepository()

    @staticmethod
    async def ensure_table() -> None:
        """Create the persona table if it does not exist yet.

        This is a safety net for environments where Alembic migrations
        have not been run (e.g. fresh dev setup). It is idempotent.
        """
        from sqlalchemy import text

        from core.db.engine import get_db_engine

        engine = get_db_engine()
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS persona (
                    id                          SERIAL PRIMARY KEY,
                    name                        TEXT NOT NULL,
                    description                 TEXT NOT NULL DEFAULT '',
                    system_prompt               TEXT NOT NULL DEFAULT '',
                    task_prompt                 TEXT NOT NULL DEFAULT '',
                    datetime_aware              BOOLEAN NOT NULL DEFAULT TRUE,
                    is_public                   BOOLEAN NOT NULL DEFAULT TRUE,
                    llm_model_provider_override TEXT,
                    llm_model_version_override  TEXT,
                    starter_messages            JSONB,
                    labels                      JSONB,
                    user_id                     TEXT NOT NULL DEFAULT 'dev-user',
                    is_builtin                  BOOLEAN NOT NULL DEFAULT FALSE,
                    builtin_key                 TEXT,
                    base_agent                  TEXT,
                    mcp_tools                   JSONB,
                    time_created                TIMESTAMPTZ NOT NULL DEFAULT now(),
                    time_updated                TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_persona_user_id ON persona (user_id)"
            ))
        logger.info("persona table ready")

    @staticmethod
    async def create(
        name: str,
        description: str = "",
        system_prompt: str = "",
        task_prompt: str = "",
        user_id: str = "dev-user",
        is_builtin: bool = False,
        builtin_key: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create a new persona."""
        return await PersonaDB._repository.create(
            name=name,
            description=description,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            user_id=user_id,
            is_builtin=is_builtin,
            builtin_key=builtin_key,
            **extra,
        )

    @staticmethod
    async def get(persona_id: int) -> dict[str, Any] | None:
        """Get a persona by ID."""
        return await PersonaDB._repository.get(persona_id)

    @staticmethod
    async def get_by_builtin_key(builtin_key: str) -> dict[str, Any] | None:
        """Get a persona by its builtin_key (maps to agents.py keys)."""
        return await PersonaDB._repository.get_by_builtin_key(builtin_key)

    @staticmethod
    async def list_all(include_builtin: bool = True) -> list[dict[str, Any]]:
        """List all personas (custom + builtin or custom only)."""
        return await PersonaDB._repository.list_all(include_builtin)

    @staticmethod
    async def list_by_user(user_id: str) -> list[dict[str, Any]]:
        """List custom personas for a user."""
        return await PersonaDB._repository.list_by_user(user_id)

    @staticmethod
    async def update(persona_id: int, **fields: Any) -> dict[str, Any] | None:
        """Update a persona."""
        return await PersonaDB._repository.update(persona_id, **fields)

    @staticmethod
    async def delete(persona_id: int) -> bool:
        """Delete a persona."""
        return await PersonaDB._repository.delete(persona_id)
