"""Database layer — SQLAlchemy 2.0 async ORM.

- **engine**        — Async engine singleton and session factory.
- **models/**       — Declarative ORM models (one file per table).
- **repositories/** — Domain-specific repository classes with typed I/O.
"""

from core.db.engine import (
    close_db_engine,
    get_async_session,
    get_db_engine,
    get_session_factory,
)
from core.db.repositories import (
    AssistantRepository,
    ThreadRepository,
    DatasourceRepository,
    ScheduleRepository,
    AirbyteMappingRepository,
)

__all__ = [
    # engine
    "close_db_engine",
    "get_async_session",
    "get_db_engine",
    "get_session_factory",
    # repositories
    "AssistantRepository",
    "ThreadRepository",
    "DatasourceRepository",
    "ScheduleRepository",
    "AirbyteMappingRepository",
]
