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
- ``agent_definitions``         — Dynamic agent composition definitions

.. note::
   LangGraph checkpoint / store tables are **not** managed here — they
   are handled internally by ``langgraph-checkpoint-postgres``.

   Chat sessions are now managed via Thread-based storage in the LangGraph store.
"""

from core.db.models.agent import AgentModel
from core.db.models.agent_definition import AgentDefinitionModel
from core.db.models.agent_group import AgentGroupModel
from core.db.models.agent_tools import AgentToolsModel
from core.db.models.airbyte_mapping import AirbyteMappingModel
from core.db.models.assistant import AssistantModel
from core.db.models.base import Base
from core.db.models.collection import PgCollection
from core.db.models.document import DocumentModel
from core.db.models.mail_config import MailConfigModel
from core.db.models.mcp_oauth_session import MCPOAuthSessionModel
from core.db.models.mcp_provider import MCPProviderModel
from core.db.models.mcp_provider_auth import MCPProviderAuthModel
from core.db.models.mcp_tool import MCPToolModel
from core.db.models.persona import PersonaModel
from core.db.models.project import ProjectModel
from core.db.models.provider import ProviderModel, UserProviderConfigModel
from core.db.models.schedule import SyncScheduleModel
from core.db.models.thread import ThreadModel


def register_external_models() -> None:
    """Import ORM models that live outside ``core.db.models`` for Alembic."""
    return None


__all__ = [
    "AgentModel",
    "Base",
    "AssistantModel",
    "ThreadModel",
    "PgCollection",
    "SyncScheduleModel",
    "AirbyteMappingModel",
    "PersonaModel",
    "ProjectModel",
    "MCPProviderModel",
    "MCPProviderAuthModel",
    "MCPOAuthSessionModel",
    "MCPToolModel",
    "MailConfigModel",
    "AgentToolsModel",
    "AgentDefinitionModel",
    "AgentGroupModel",
    "DocumentModel",
    "ProviderModel",
    "UserProviderConfigModel",
    "register_external_models",
]
