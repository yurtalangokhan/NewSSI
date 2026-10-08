"""Boundary checks for the slimmed ``agents`` runtime package."""

from pathlib import Path

AGENT_SERVICE_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = AGENT_SERVICE_ROOT / "src"


def test_agent_definition_storage_uses_repository_and_core_model_layers() -> None:
    """Agent-definition persistence must not live under the runtime agents package."""
    assert (SRC_ROOT / "infrastructure/db/models/agent_definition.py").is_file()
    assert (SRC_ROOT / "infrastructure/db/repositories/agent_definition_repo.py").is_file()
    assert not (SRC_ROOT / "agents/storage").exists()

    from infrastructure.db.models.agent_definition import AgentDefinitionModel
    from infrastructure.db.repositories.agent_definition_repo import AgentDefinitionRepository

    assert AgentDefinitionModel.__tablename__ == "agent_definitions"
    assert AgentDefinitionRepository.__name__ == "AgentDefinitionRepository"


def test_agent_service_has_no_local_tools_module() -> None:
    """``agents/tools.py`` used to hold, in turn, a local calculator tool, an
    unused request-context tool, local RAG search wrappers, and finally raw
    Milvus/embeddings connection code for the datasource pipeline — each
    stripped out as its equivalent moved to tools-service or rag-service.
    The last of those (Milvus access) moved to rag-service's
    ``/datasources/{id}/records`` and ``/datasources/{id}/entities``
    endpoints, called via ``client.rag_client``, leaving nothing left to
    strip: the module itself is gone.
    """
    assert not (SRC_ROOT / "agents/tools.py").exists()
