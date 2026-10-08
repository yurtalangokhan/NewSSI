"""Tests for api.helpers modules.

Validates pure, stateless helper functions extracted from route files.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from langgraph.types import Send

from api.helpers.agent_definition_helpers import (
    definition_to_dict,
    filter_available_agents_by_schema,
    normalize_schema_name,
)
from api.helpers.assistant_helpers import agent_to_assistant
from api.helpers.chat_route_helpers import parse_resume_position
from api.helpers.file_helpers import file_not_found_exception, safe_content_disposition
from api.helpers.flow_helpers import version_to_dict
from api.helpers.mcp_admin_helpers import (
    numeric_id_for,
    server_config,
    to_mcp_server,
)
from api.helpers.thread_helpers import sanitize_checkpoint_values

# =========================================================================
# Assistant Helpers
# =========================================================================


def test_agent_to_assistant():
    res = agent_to_assistant("agent-123", "Test Agent Description")
    assert res["assistant_id"] == "agent-123"
    assert res["graph_id"] == "agent-123"
    assert res["metadata"]["description"] == "Test Agent Description"
    assert res["metadata"]["_x_oap_is_default"] is True
    assert "created_at" in res
    assert "updated_at" in res


# =========================================================================
# Agent Definition Helpers
# =========================================================================


def test_normalize_schema_name():
    assert normalize_schema_name("react") == "REACT"
    assert normalize_schema_name("  Supervisor  ") == "SUPERVISOR"
    assert normalize_schema_name(None) is None
    assert normalize_schema_name("") is None


def test_filter_available_agents_by_schema():
    agents = [
        {"key": "a1", "graph_schema": "REACT"},
        {"key": "a2", "graph_schema": "FLOW"},
        {"key": "a3", "graph_schema": "SUPERVISOR"},
        {"key": "a4", "graph_schema": "PIPELINE"},
    ]
    # FLOW is always filtered out
    unfiltered = filter_available_agents_by_schema(agents, None)
    assert len(unfiltered) == 3
    assert all(a["graph_schema"] != "FLOW" for a in unfiltered)

    supervisor_filtered = filter_available_agents_by_schema(agents, "SUPERVISOR")
    keys = [a["key"] for a in supervisor_filtered]
    assert "a1" in keys
    assert "a3" in keys
    assert "a4" not in keys

    pipeline_filtered = filter_available_agents_by_schema(agents, "PIPELINE")
    p_keys = [a["key"] for a in pipeline_filtered]
    assert "a1" in p_keys
    assert "a3" not in p_keys
    assert "a4" not in p_keys


def test_definition_to_dict():
    mock_def = SimpleNamespace(
        id=uuid4(),
        persona_id=10,
        name="test-def",
        agent_type="custom",
        description="desc",
        graph_schema="REACT",
        brain_type="standard",
        memory_type="summary",
        system_prompt="prompt",
        model="gpt-4o",
        mcp_tools=["t1"],
        rag_config=None,
        sub_agents=None,
        sub_agent_ids=None,
        supervisor_prompt=None,
        stages=None,
        pipeline_prompt=None,
        reflection_prompt=None,
        max_iterations=5,
        version=1,
        tags=["tag1"],
        is_active=True,
        created_at=None,
        updated_at=None,
    )
    d = definition_to_dict(mock_def)
    assert d["id"] == str(mock_def.id)
    assert d["name"] == "test-def"
    assert d["rag_config"] == {"document_processing": [], "knowledge_graph": []}
    assert d["sub_agents"] == []


# =========================================================================
# MCP Admin Helpers
# =========================================================================


def test_numeric_id_for():
    id1 = numeric_id_for("123e4567-e89b-12d3-a456-426614174000")
    id2 = numeric_id_for("123e4567-e89b-12d3-a456-426614174000")
    id3 = numeric_id_for("987fcdeb-51a2-43f7-9abc-def012345678")
    assert isinstance(id1, int)
    assert id1 == id2
    assert id1 != id3
    assert id1 > 0


def test_server_config():
    assert server_config({"config": {"auth_type": "BEARER"}}) == {"auth_type": "BEARER"}
    assert server_config({}) == {}
    assert server_config({"config": None}) == {}


def test_to_mcp_server():
    provider = {
        "int_id": 42,
        "id": "uuid-1",
        "name": "Test MCP",
        "description": "Desc",
        "url": "http://localhost:8000",
        "config": {"auth_type": "NONE", "status": "CONNECTED"},
    }
    dto = to_mcp_server(provider, tool_count=5)
    assert dto["id"] == 42
    assert dto["provider_id"] == "uuid-1"
    assert dto["name"] == "Test MCP"
    assert dto["tool_count"] == 5
    assert dto["is_authenticated"] is True


# =========================================================================
# File Helpers
# =========================================================================


def test_file_not_found_exception():
    exc = file_not_found_exception()
    assert exc.status_code == 404
    assert exc.headers.get("Cache-Control") == "no-store"


def test_safe_content_disposition():
    ascii_res = safe_content_disposition("attachment", "document.pdf")
    assert ascii_res == 'attachment; filename="document.pdf"'

    unicode_res = safe_content_disposition("inline", "rapor_şöğü.pdf")
    assert "filename*=" in unicode_res
    assert "UTF-8''" in unicode_res


# =========================================================================
# Flow Helpers
# =========================================================================


def test_version_to_dict():
    mock_ver = SimpleNamespace(
        id=uuid4(),
        definition_id=uuid4(),
        version_no=2,
        status="published",
        created_by="user-1",
        published_by="user-1",
        created_at=None,
        published_at=None,
        notes="v2 release",
    )
    res = version_to_dict(mock_ver)
    assert res["id"] == str(mock_ver.id)
    assert res["version_no"] == 2
    assert res["status"] == "published"
    assert res["notes"] == "v2 release"


# =========================================================================
# Thread Helpers
# =========================================================================


def test_sanitize_checkpoint_values():
    send_obj = Send(node="agent_node", arg={"data": "test"})
    values = {
        "text": "hello",
        "send_call": send_obj,
        "list_with_send": ["a", send_obj, "b"],
        "nested": {
            "key": "val",
            "send": send_obj,
        },
    }
    sanitized = sanitize_checkpoint_values(values)
    assert sanitized["text"] == "hello"
    assert sanitized["send_call"]["__type__"] == "Send"
    assert sanitized["send_call"]["node"] == "agent_node"
    assert sanitized["list_with_send"][1]["__type__"] == "Send"
    assert sanitized["nested"]["send"]["__type__"] == "Send"


@pytest.mark.parametrize(
    ("header", "after", "expected"),
    [(None, 0, 0), (None, 7, 7), ("12", 0, 12), (" 3 ", 9, 3), ("", 4, 4)],
)
def test_parse_resume_position_prefers_last_event_id(header, after, expected):
    assert parse_resume_position(header, after) == expected


@pytest.mark.parametrize("header", ["abc", "-1", "1.5", "0-12"])
def test_parse_resume_position_rejects_malformed_ids(header):
    with pytest.raises(ValueError):
        parse_resume_position(header, 0)
