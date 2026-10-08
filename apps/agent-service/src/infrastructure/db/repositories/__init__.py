"""PostgreSQL repository classes — the one location for agent-service persistence.

Each repository encapsulates typed CRUD for one domain table. All inherit from
:class:`BaseRepository`, which provides the ``_session()`` (commit/rollback) and
``_read_session()`` (AUTOCOMMIT) context managers.

This package is the *only* repository location: the three modules that used to
live in a second package (``repository/``) and the one that lived under
``service/providers/`` were moved here, so "where is the query for table X?" has
a single answer. ``tests/core/test_repository_style.py`` enforces the location.

``domain/`` and ``agents/`` cannot import this package at all (architecture
gate); they reach it through ``core.persistence_gateway``.

Usage::

    from infrastructure.db.repositories import AgentRepository

    repo = AgentRepository()
    agents = await repo.list_all()
"""

from infrastructure.db.repositories.agent_definition_repo import AgentDefinitionRepository
from infrastructure.db.repositories.agent_repo import AgentRepository
from infrastructure.db.repositories.agent_tools_repo import AgentToolsRepository
from infrastructure.db.repositories.assistant_repo import AssistantRepository
from infrastructure.db.repositories.authored_document_repo import AuthoredDocumentRepository
from infrastructure.db.repositories.base import BaseRepository
from infrastructure.db.repositories.connector_sync_repo import (
    ConnectorSyncJobRepository,
    ConnectorSyncStateRepository,
)
from infrastructure.db.repositories.datasource_connection_repo import DatasourceConnectionRepository
from infrastructure.db.repositories.datasource_repo import DatasourceRepository
from infrastructure.db.repositories.document_repo import DocumentRepository
from infrastructure.db.repositories.flow_version_repo import FlowSummary, FlowVersionRepository
from infrastructure.db.repositories.knowledge_evidence_repo import KnowledgeEvidenceRepository
from infrastructure.db.repositories.mail_config_repo import MailConfigRepository
from infrastructure.db.repositories.mcp_oauth_session_repo import MCPOAuthSessionRepository
from infrastructure.db.repositories.mcp_provider_auth_repo import MCPProviderAuthRepository
from infrastructure.db.repositories.mcp_provider_repo import MCPProviderRepository
from infrastructure.db.repositories.mcp_tool_repo import MCPToolRepository
from infrastructure.db.repositories.persona_repo import PersonaRepository
from infrastructure.db.repositories.project_repo import ProjectRepository
from infrastructure.db.repositories.provider_repo import ProviderRepository
from infrastructure.db.repositories.schedule_repo import ScheduleRepository
from infrastructure.db.repositories.thread_repo import ThreadRepository
from infrastructure.db.repositories.user_mail_credential_repo import UserMailCredentialRepository

__all__ = [
    "AgentDefinitionRepository",
    "AgentRepository",
    "AgentToolsRepository",
    "AssistantRepository",
    "AuthoredDocumentRepository",
    "BaseRepository",
    "ConnectorSyncJobRepository",
    "ConnectorSyncStateRepository",
    "DatasourceConnectionRepository",
    "DatasourceRepository",
    "DocumentRepository",
    "FlowSummary",
    "FlowVersionRepository",
    "KnowledgeEvidenceRepository",
    "MCPOAuthSessionRepository",
    "MCPProviderAuthRepository",
    "MCPProviderRepository",
    "MCPToolRepository",
    "MailConfigRepository",
    "PersonaRepository",
    "ProjectRepository",
    "ProviderRepository",
    "ScheduleRepository",
    "ThreadRepository",
    "UserMailCredentialRepository",
]
