"""Repository accessors for the domain and agent layers.

The architecture gate (docs/oop-solid-architecture.md, enforced by
``scripts/quality/check_architecture.py``) keeps ``domain/`` and ``agents/``
from importing a concrete ``repository``/``core.db`` module: the dependency
must point inward, so those layers ask for persistence instead of naming it.

Every accessor imports its repository lazily, inside the call. That keeps the
import cycles that forced the original function-local imports broken, and it
keeps ``monkeypatch.setattr("repository.<module>.<Class>", ...)`` working,
because the class is looked up on its own module at call time.
"""

from __future__ import annotations

from typing import Any


def agent_definition_repository() -> Any:
    """A repository over ``agent_definitions``."""
    from repository.agent_definition_repository import AgentDefinitionRepository

    return AgentDefinitionRepository()


def flow_version_repository() -> Any:
    """A repository over ``agent_flow_versions`` (drafts and published versions)."""
    from repository.flow_version_repository import FlowVersionRepository

    return FlowVersionRepository()


def persona_db() -> Any:
    """The ``PersonaDB`` facade (a class of static/classmethods, not an instance)."""
    from repository.persona_repository import PersonaDB

    return PersonaDB


def persona_repository() -> Any:
    """A repository over ``persona``."""
    from core.db.repositories.persona_repo import PersonaRepository

    return PersonaRepository()


def document_repository() -> Any:
    """A repository over uploaded/generated ``document`` rows."""
    from core.db.repositories.document_repo import DocumentRepository

    return DocumentRepository()


def mcp_provider_repository_class() -> Any:
    """The MCP provider repository class (callers construct it themselves)."""
    from core.db.repositories import MCPProviderRepository

    return MCPProviderRepository


def mcp_tool_repository_class() -> Any:
    """The MCP tool repository class (callers construct it themselves)."""
    from core.db.repositories import MCPToolRepository

    return MCPToolRepository


async def list_rag_collection_rows() -> list[Any]:
    """``(uuid, name, cmetadata)`` for every RAG collection, ordered by name.

    The rag-service owns these rows; this is the direct-DB fallback used when
    its API is unreachable, and it lives here so the flow resolvers never
    touch a model class.
    """
    from sqlalchemy import select

    from core.db.models.collection import PgCollection
    from core.db.repositories.base import BaseRepository

    class _CollectionLookupRepo(BaseRepository):
        async def list_all(self) -> list[Any]:
            async with self._session() as session:
                stmt = select(
                    PgCollection.uuid, PgCollection.name, PgCollection.cmetadata
                ).order_by(PgCollection.name)
                result = await session.execute(stmt)
                return list(result.all())

    return await _CollectionLookupRepo().list_all()
