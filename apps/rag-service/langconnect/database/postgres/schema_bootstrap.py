"""Postgres schema bootstrap for LangConnect.

Creates service-owned metadata tables when missing so local startup does not
require manual migration execution.
"""

from __future__ import annotations

import logging

from langconnect.database.postgres.engine import get_db_engine
from langconnect.database.postgres.models import Base

logger = logging.getLogger(__name__)


async def ensure_schema() -> None:
    """Create LangConnect tables if absent in the configured database."""
    engine = get_db_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("LangConnect schema bootstrap completed.")
