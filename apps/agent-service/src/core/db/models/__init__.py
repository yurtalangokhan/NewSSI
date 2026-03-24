"""SQLAlchemy 2.0 declarative ORM models.

All table models are defined in separate modules for clarity.
This ``__init__`` re-exports everything so consumers can do::

    from core.db.models import Base, AssistantModel, ThreadModel, ...

Alembic ``autogenerate`` reads ``Base.metadata`` from here — all
model modules **must** be imported so their tables are registered
on the shared ``Base``.

Tables managed here
-------------------
- ``assistant``                  — Agent assistant definitions
- ``thread``                     — Conversation threads with JSONB metadata
- ``langchain_pg_collection``    — Vector store collections (datasource metadata)
- ``langchain_pg_embedding``     — Document embeddings / chunks
- ``sync_schedules``             — Cron-based sync schedule definitions
- ``datasource_airbyte_mapping`` — Local → Airbyte ID mapping with job watermark

.. note::
   LangGraph checkpoint / store tables are **not** managed here — they
   are handled internally by ``langgraph-checkpoint-postgres``.
"""

from core.db.models.base import Base
from core.db.models.assistant import AssistantModel
from core.db.models.thread import ThreadModel
from core.db.models.collection import PgCollection, PgEmbedding
from core.db.models.schedule import SyncScheduleModel
from core.db.models.airbyte_mapping import AirbyteMappingModel

__all__ = [
    "Base",
    "AssistantModel",
    "ThreadModel",
    "PgCollection",
    "PgEmbedding",
    "SyncScheduleModel",
    "AirbyteMappingModel",
]
