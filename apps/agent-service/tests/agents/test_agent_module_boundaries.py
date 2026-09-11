"""Boundary checks for the slimmed ``agents`` runtime package."""

from pathlib import Path

AGENT_SERVICE_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = AGENT_SERVICE_ROOT / "src"


def test_agent_definition_storage_uses_repository_and_core_model_layers() -> None:
    """Agent-definition persistence must not live under the runtime agents package."""
    assert (SRC_ROOT / "core/db/models/agent_definition.py").is_file()
    assert (SRC_ROOT / "repository/agent_definition_repository.py").is_file()
    assert not (SRC_ROOT / "agents/storage").exists()

    from core.db.models.agent_definition import AgentDefinitionModel
    from repository.agent_definition_repository import AgentDefinitionRepository

    assert AgentDefinitionModel.__tablename__ == "agent_definitions"
    assert AgentDefinitionRepository.__name__ == "AgentDefinitionRepository"


def test_agent_service_does_not_keep_local_calculator_tool() -> None:
    """Generic tools with tools-service equivalents must not live in agent-service."""
    source = (SRC_ROOT / "agents/tools.py").read_text()

    assert "def calculator_func" not in source
    assert "calculator: BaseTool" not in source


def test_agent_service_does_not_keep_unused_context_tool() -> None:
    """Request/user context belongs in trusted runtime config, not a local tool."""
    source = (SRC_ROOT / "agents/tools.py").read_text()

    assert "def get_current_user_id" not in source


def test_agent_service_does_not_keep_local_rag_tool_wrappers() -> None:
    """RAG search tools are tools-service capabilities backed by rag-service."""
    source = (SRC_ROOT / "agents/tools.py").read_text()

    assert "def database_search_func" not in source
    assert "def graph_search_func" not in source
    assert "database_search: BaseTool" not in source
    assert "graph_search: BaseTool" not in source
