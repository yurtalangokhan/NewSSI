"""PostgreSQL repository classes.

Each repository encapsulates typed CRUD for one domain table.
All inherit from :class:`BaseRepository` which provides the
``_session()`` async context manager (commit / rollback).

Usage::

    from core.db.repositories import AgentRepository

    repo = AgentRepository()
    agents = await repo.list_all()
"""

from core.db.repositories.agent_group_repo import AgentGroupRepository
from core.db.repositories.agent_repo import AgentRepository
from core.db.repositories.agent_tools_repo import AgentToolsRepository
from core.db.repositories.airbyte_mapping_repo import AirbyteMappingRepository
from core.db.repositories.assistant_repo import AssistantRepository
from core.db.repositories.base import BaseRepository
from core.db.repositories.datasource_repo import DatasourceRepository
from core.db.repositories.mail_config_repo import MailConfigRepository
from core.db.repositories.mcp_oauth_session_repo import MCPOAuthSessionRepository
from core.db.repositories.mcp_provider_auth_repo import MCPProviderAuthRepository
from core.db.repositories.mcp_provider_repo import MCPProviderRepository
from core.db.repositories.mcp_tool_repo import MCPToolRepository
from core.db.repositories.persona_repo import PersonaRepository
from core.db.repositories.project_repo import ProjectRepository
from core.db.repositories.schedule_repo import ScheduleRepository
from core.db.repositories.thread_repo import ThreadRepository

__all__ = [
    "AgentRepository",
    "BaseRepository",
    "AssistantRepository",
    "ThreadRepository",
    "DatasourceRepository",
    "ScheduleRepository",
    "AirbyteMappingRepository",
    "PersonaRepository",
    "ProjectRepository",
    "MCPProviderRepository",
    "MCPProviderAuthRepository",
    "MCPOAuthSessionRepository",
    "MCPToolRepository",
    "MailConfigRepository",
    "AgentToolsRepository",
    "AgentGroupRepository",
]
