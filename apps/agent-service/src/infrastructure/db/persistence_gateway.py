"""Repository accessors — the typed entry point for code outside the data layer.

The architecture gate (docs/oop-solid-architecture.md, enforced by
``scripts/quality/check_architecture.py``) keeps ``domain/`` and ``agents/``
from importing a concrete ``repository``/``infrastructure.db`` module: the dependency
must point inward, so those layers ask for persistence instead of naming it.
This module therefore lives in ``core/`` — next to ``core.logger``/``core.http``,
which those layers already depend on — and not in ``repository/``: importing
*any* ``repository`` module from ``domain/`` is a HARD finding, gateway or not.

The service layer uses it too, as the single way to *obtain* a repository.
``tests/core/test_repository_style.py`` enforces that no service module imports
a repository class at runtime — an accessor that is missing here, or a door
that is incomplete, is what pushes a caller back to a direct import.

Every accessor imports its repository lazily, inside the call. That keeps the
import cycles that forced the original function-local imports broken, and it
keeps ``monkeypatch.setattr("infrastructure.db.repositories.<module>.<Class>", ...)``
working, because the class is looked up on its own module at call time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Types only. The runtime imports stay inside each accessor so that naming
    # this module never drags the whole repository package in: the agents/ and
    # domain/ layers import it at module scope, and a repository module that
    # later grows an outward import must not be able to close a cycle here.
    from infrastructure.db.repositories import (
        AgentDefinitionRepository,
        AgentRepository,
        AgentToolsRepository,
        AssistantRepository,
        AuthoredDocumentRepository,
        ConnectorSyncJobRepository,
        ConnectorSyncStateRepository,
        DatasourceConnectionRepository,
        DatasourceRepository,
        DocumentRepository,
        FlowVersionRepository,
        KnowledgeEvidenceRepository,
        MailConfigRepository,
        MCPOAuthSessionRepository,
        MCPProviderAuthRepository,
        MCPProviderRepository,
        MCPToolRepository,
        PersonaRepository,
        ProjectRepository,
        ProviderRepository,
        ScheduleRepository,
        ThreadRepository,
        UserMailCredentialRepository,
    )


# ---------------------------------------------------------------------------
# One accessor per repository over one table
# ---------------------------------------------------------------------------
# "How do I reach table X?" has the same answer everywhere. The guard test
# asserts this list stays complete, one accessor per exported repository class.


def agent_definition_repository() -> AgentDefinitionRepository:
    """A repository over ``agent_definitions``."""
    from infrastructure.db.repositories.agent_definition_repo import AgentDefinitionRepository

    return AgentDefinitionRepository()


def agent_repository() -> AgentRepository:
    """A repository over ``agents``."""
    from infrastructure.db.repositories.agent_repo import AgentRepository

    return AgentRepository()


def agent_tools_repository() -> AgentToolsRepository:
    """A repository over the agent↔tool binding table."""
    from infrastructure.db.repositories.agent_tools_repo import AgentToolsRepository

    return AgentToolsRepository()


def assistant_repository() -> AssistantRepository:
    """A repository over ``assistants``."""
    from infrastructure.db.repositories.assistant_repo import AssistantRepository

    return AssistantRepository()


def authored_document_repository() -> AuthoredDocumentRepository:
    """A repository over ``authored_documents`` and their revisions."""
    from infrastructure.db.repositories.authored_document_repo import AuthoredDocumentRepository

    return AuthoredDocumentRepository()


def connector_sync_job_repository() -> ConnectorSyncJobRepository:
    """A repository over ``connector_sync_jobs``."""
    from infrastructure.db.repositories.connector_sync_repo import ConnectorSyncJobRepository

    return ConnectorSyncJobRepository()


def connector_sync_state_repository() -> ConnectorSyncStateRepository:
    """A repository over ``connector_sync_state`` (incremental checkpoints)."""
    from infrastructure.db.repositories.connector_sync_repo import ConnectorSyncStateRepository

    return ConnectorSyncStateRepository()


def datasource_connection_repository() -> DatasourceConnectionRepository:
    """A repository over ``datasource_connections`` (connector + stream catalog)."""
    from infrastructure.db.repositories.datasource_connection_repo import (
        DatasourceConnectionRepository,
    )

    return DatasourceConnectionRepository()


def datasource_repository() -> DatasourceRepository:
    """A repository over the RAG collection/datasource tables."""
    from infrastructure.db.repositories.datasource_repo import DatasourceRepository

    return DatasourceRepository()


def document_repository() -> DocumentRepository:
    """A repository over uploaded/generated ``document`` rows."""
    from infrastructure.db.repositories.document_repo import DocumentRepository

    return DocumentRepository()


def flow_version_repository() -> FlowVersionRepository:
    """A repository over ``agent_flow_versions`` (drafts and published versions)."""
    from infrastructure.db.repositories.flow_version_repo import FlowVersionRepository

    return FlowVersionRepository()


def knowledge_evidence_repository() -> KnowledgeEvidenceRepository:
    """A repository over thread-scoped ``knowledge_evidence`` rows."""
    from infrastructure.db.repositories.knowledge_evidence_repo import KnowledgeEvidenceRepository

    return KnowledgeEvidenceRepository()


def mail_config_repository() -> MailConfigRepository:
    """A repository over ``mail_configs``."""
    from infrastructure.db.repositories.mail_config_repo import MailConfigRepository

    return MailConfigRepository()


def mcp_oauth_session_repository() -> MCPOAuthSessionRepository:
    """A repository over ``mcp_oauth_sessions``."""
    from infrastructure.db.repositories.mcp_oauth_session_repo import MCPOAuthSessionRepository

    return MCPOAuthSessionRepository()


def mcp_provider_auth_repository() -> MCPProviderAuthRepository:
    """A repository over the MCP provider credential table."""
    from infrastructure.db.repositories.mcp_provider_auth_repo import MCPProviderAuthRepository

    return MCPProviderAuthRepository()


def mcp_provider_repository() -> MCPProviderRepository:
    """A repository over ``mcp_providers``."""
    from infrastructure.db.repositories.mcp_provider_repo import MCPProviderRepository

    return MCPProviderRepository()


def mcp_provider_repository_class() -> Any:
    """The MCP provider repository class (callers construct it themselves).

    ``agents/mcp_external.py`` binds the class as a module attribute so tests can
    substitute it by patching that name: it needs the class, not an instance.
    """
    from infrastructure.db.repositories.mcp_provider_repo import MCPProviderRepository

    return MCPProviderRepository


def mcp_tool_repository() -> MCPToolRepository:
    """A repository over ``mcp_tools``."""
    from infrastructure.db.repositories.mcp_tool_repo import MCPToolRepository

    return MCPToolRepository()


def mcp_tool_repository_class() -> Any:
    """The MCP tool repository class (callers construct it themselves)."""
    from infrastructure.db.repositories.mcp_tool_repo import MCPToolRepository

    return MCPToolRepository


def persona_repository() -> PersonaRepository:
    """A repository over ``persona``."""
    from infrastructure.db.repositories.persona_repo import PersonaRepository

    return PersonaRepository()


def project_repository() -> ProjectRepository:
    """A repository over ``projects``."""
    from infrastructure.db.repositories.project_repo import ProjectRepository

    return ProjectRepository()


def provider_repository() -> ProviderRepository:
    """A repository over ``providers`` / ``user_provider_configs``.

    ``service/providers/service.py`` only needs the *shape* (its
    ``ProviderRepositoryPort``); this is how the flow resolvers hand it the real
    one without naming it.
    """
    from infrastructure.db.repositories.provider_repo import ProviderRepository

    return ProviderRepository()


def schedule_repository() -> ScheduleRepository:
    """A repository over ``sync_schedules``."""
    from infrastructure.db.repositories.schedule_repo import ScheduleRepository

    return ScheduleRepository()


def thread_repository() -> ThreadRepository:
    """A repository over ``threads``."""
    from infrastructure.db.repositories.thread_repo import ThreadRepository

    return ThreadRepository()


def user_mail_credential_repository() -> UserMailCredentialRepository:
    """A repository over the per-user mail credential table."""
    from infrastructure.db.repositories.user_mail_credential_repo import (
        UserMailCredentialRepository,
    )

    return UserMailCredentialRepository()


async def list_rag_collection_rows() -> list[Any]:
    """``(uuid, name, cmetadata)`` for every RAG collection, ordered by name.

    The rag-service owns these rows; this is the direct-DB fallback used when
    its API is unreachable, and it lives here so the flow resolvers never
    touch a model class.
    """
    from sqlalchemy import select

    from infrastructure.db.models.collection import PgCollection
    from infrastructure.db.repositories.base import BaseRepository

    class _CollectionLookupRepo(BaseRepository):
        async def list_all(self) -> list[Any]:
            async with self._read_session() as session:
                stmt = select(PgCollection.uuid, PgCollection.name, PgCollection.cmetadata).order_by(PgCollection.name)
                result = await session.execute(stmt)
                return list(result.all())

    return await _CollectionLookupRepo().list_all()
