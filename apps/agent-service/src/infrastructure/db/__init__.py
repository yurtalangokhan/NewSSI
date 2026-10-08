"""Database layer — SQLAlchemy 2.0 async ORM.

- **engine**        — Async engine singleton and session factory.
- **models/**       — Declarative ORM models (one file per table).
- **repositories/** — Domain-specific repository classes with typed I/O.
"""

from infrastructure.db.engine import (
    close_db_engine,
    get_async_session,
    get_db_engine,
    get_pool_status,
    get_session_factory,
)
from infrastructure.db.repositories import (
    AssistantRepository,
    DatasourceRepository,
    ProjectRepository,
    ScheduleRepository,
    ThreadRepository,
)

__all__ = [
    # repositories
    "AssistantRepository",
    "DatasourceRepository",
    "ProjectRepository",
    "ScheduleRepository",
    "ThreadRepository",
    # engine
    "close_db_engine",
    "get_async_session",
    "get_db_engine",
    "get_pool_status",
    "get_session_factory",
]
