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
- ``persona``                   — Custom agent/persona configurations

.. note::
   LangGraph checkpoint / store tables are **not** managed here — they
   are handled internally by ``langgraph-checkpoint-postgres``.

   Chat sessions are now managed via Thread-based storage in the LangGraph store.
"""

from core.db.models.airbyte_mapping import AirbyteMappingModel
from core.db.models.assistant import AssistantModel
from core.db.models.agent_tools import AgentToolsModel
from core.db.models.base import Base
from core.db.models.collection import PgCollection, PgEmbedding
from core.db.models.mcp_provider import MCPProviderModel
from core.db.models.mcp_tool import MCPToolModel
from core.db.models.persona import PersonaModel
from core.db.models.project import ProjectModel
from core.db.models.schedule import SyncScheduleModel
from core.db.models.thread import ThreadModel
from core.db.models.user_settings import UserSettingsModel

__all__ = [
    "Base",
    "AssistantModel",
    "ThreadModel",
    "PgCollection",
    "PgEmbedding",
    "SyncScheduleModel",
    "AirbyteMappingModel",
    "PersonaModel",
    "ProjectModel",
    "MCPProviderModel",
    "MCPToolModel",
    "AgentToolsModel",
    "UserSettingsModel",
]
