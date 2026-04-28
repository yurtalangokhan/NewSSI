"""Schema bootstrap helpers for development/runtime safety.

Ensures service-owned tables exist in the configured database without
requiring a manual Alembic run during local startup.
"""

from __future__ import annotations

import logging

from core.db.engine import get_db_engine
from core.db.models import Base

logger = logging.getLogger(__name__)


async def ensure_schema() -> None:
    """Create service-owned tables if they are missing.

    This is idempotent and scoped to the current service database
    (determined by POSTGRES_DB).
    """
    engine = get_db_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Agent service schema bootstrap completed.")
