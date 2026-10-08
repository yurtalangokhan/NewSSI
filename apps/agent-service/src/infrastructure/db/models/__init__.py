"""SQLAlchemy 2.0 declarative ORM models.

All table models are defined in separate modules for clarity.
This ``__init__`` re-exports everything so consumers can do::

    from infrastructure.db.models import Base, AssistantModel, ThreadModel, ...

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
- ``datasource_connections``     — Connector + stream catalog of a datasource
- ``connector_sync_jobs``        — Sync job history
- ``connector_sync_state``       — Incremental sync checkpoints
- ``persona``                   — Custom agent/persona configurations
- ``agent_definitions``         — Dynamic agent composition definitions
- ``knowledge_evidence``         — Chunks/subgraph each knowledge retrieval call used
- ``authored_documents``        — Versioned, agent-editable document drafts
- ``authored_document_revisions`` — Revision history for authored documents

.. note::
   LangGraph checkpoint / store tables are **not** managed here — they
   are handled internally by ``langgraph-checkpoint-postgres``.

   Chat sessions are now managed via Thread-based storage in the LangGraph store.
"""

from infrastructure.db.models.agent import AgentModel
from infrastructure.db.models.agent_definition import AgentDefinitionModel
from infrastructure.db.models.agent_tools import AgentToolsModel
from infrastructure.db.models.assistant import AssistantModel
from infrastructure.db.models.authored_document import AuthoredDocumentModel, AuthoredDocumentRevisionModel
from infrastructure.db.models.base import Base
from infrastructure.db.models.collection import PgCollection
from infrastructure.db.models.connector_sync import ConnectorSyncJobModel, ConnectorSyncStateModel
from infrastructure.db.models.datasource_connection import DatasourceConnectionModel
from infrastructure.db.models.document import DocumentModel
from infrastructure.db.models.knowledge_evidence import KnowledgeEvidenceModel
from infrastructure.db.models.mail_config import MailConfigModel
from infrastructure.db.models.mcp_oauth_session import MCPOAuthSessionModel
from infrastructure.db.models.mcp_provider import MCPProviderModel
from infrastructure.db.models.mcp_provider_auth import MCPProviderAuthModel
from infrastructure.db.models.mcp_tool import MCPToolModel
from infrastructure.db.models.persona import PersonaModel
from infrastructure.db.models.project import ProjectModel
from infrastructure.db.models.provider import ProviderModel, UserProviderConfigModel
from infrastructure.db.models.schedule import SyncScheduleModel
from infrastructure.db.models.thread import ThreadModel


def register_external_models() -> None:
    """Import ORM models that live outside ``infrastructure.db.models`` for Alembic."""
    return None


__all__ = [
    "AgentDefinitionModel",
    "AgentModel",
    "AgentToolsModel",
    "AssistantModel",
    "AuthoredDocumentModel",
    "AuthoredDocumentRevisionModel",
    "Base",
    "ConnectorSyncJobModel",
    "ConnectorSyncStateModel",
    "DatasourceConnectionModel",
    "DocumentModel",
    "KnowledgeEvidenceModel",
    "MCPOAuthSessionModel",
    "MCPProviderAuthModel",
    "MCPProviderModel",
    "MCPToolModel",
    "MailConfigModel",
    "PersonaModel",
    "PgCollection",
    "ProjectModel",
    "ProviderModel",
    "SyncScheduleModel",
    "ThreadModel",
    "UserProviderConfigModel",
    "register_external_models",
]
