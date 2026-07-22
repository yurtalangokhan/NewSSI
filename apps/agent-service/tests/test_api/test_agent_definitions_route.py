"""Tests for agent definitions route helpers."""

from api.routes.AgentDefinitionsRoute import (
    _filter_available_agents_by_schema,
    _normalize_schema_name,
)


def test_normalize_schema_name_case_insensitive() -> None:
    """Schema normalization should support lowercase frontend values."""
    assert _normalize_schema_name("supervisor") == "SUPERVISOR"
    assert _normalize_schema_name(" pipeline ") == "PIPELINE"


def test_filter_available_agents_by_schema_supervisor_lowercase() -> None:
    """Lowercase supervisor schema should return eligible nested agents."""
    agents = [
        {"id": "1", "graph_schema": "REACT"},
        {"id": "2", "graph_schema": "PLAN_EXECUTE"},
        {"id": "3", "graph_schema": "SUPERVISOR"},
        {"id": "4", "graph_schema": "PIPELINE"},
    ]

    filtered = _filter_available_agents_by_schema(agents, "supervisor")

    assert [agent["id"] for agent in filtered] == ["1", "2", "3"]


def test_filter_available_agents_by_schema_pipeline_lowercase() -> None:
    """Lowercase pipeline schema should exclude nested multi-agent schemas."""
    agents = [
        {"id": "1", "graph_schema": "REACT"},
        {"id": "2", "graph_schema": "PLAN_EXECUTE"},
        {"id": "3", "graph_schema": "SUPERVISOR"},
        {"id": "4", "graph_schema": "PIPELINE"},
        {"id": "5", "graph_schema": "ZERO_SHOT"},
    ]

    filtered = _filter_available_agents_by_schema(agents, "pipeline")

    assert [agent["id"] for agent in filtered] == ["1", "2", "5"]
