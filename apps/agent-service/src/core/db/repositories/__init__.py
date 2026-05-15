"""PostgreSQL repository classes.

Each repository encapsulates typed CRUD for one domain table.
All inherit from :class:`BaseRepository` which provides the
``_session()`` async context manager (commit / rollback).

Usage::

    from core.db.repositories import AssistantRepository

    repo = AssistantRepository()
    assistants = await repo.list_assistants()
"""

from core.db.repositories.agent_tools_repo import AgentToolsRepository
from core.db.repositories.airbyte_mapping_repo import AirbyteMappingRepository
from core.db.repositories.assistant_repo import AssistantRepository
from core.db.repositories.base import BaseRepository
from core.db.repositories.datasource_repo import DatasourceRepository
from core.db.repositories.mcp_provider_repo import MCPProviderRepository
from core.db.repositories.mcp_tool_repo import MCPToolRepository
from core.db.repositories.persona_repo import PersonaRepository
from core.db.repositories.schedule_repo import ScheduleRepository
from core.db.repositories.thread_repo import ThreadRepository

__all__ = [
    "BaseRepository",
    "AssistantRepository",
    "ThreadRepository",
    "DatasourceRepository",
    "ScheduleRepository",
    "AirbyteMappingRepository",
    "PersonaRepository",
    "MCPProviderRepository",
    "MCPToolRepository",
    "AgentToolsRepository",
]
