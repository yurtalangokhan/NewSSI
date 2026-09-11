"""Validation tests for the MCP admin API pydantic models (plan task 7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_upsert_body_normalizes_transport():
    from models.mcp_admin import MCPServerUpsertBody

    body = MCPServerUpsertBody(
        name="n", server_url="https://x/mcp", transport="streamable-http", auth_type="OAUTH"
    )
    assert body.transport == "STREAMABLE_HTTP"


def test_upsert_body_accepts_sse_case_insensitive():
    from models.mcp_admin import MCPServerUpsertBody

    body = MCPServerUpsertBody(
        name="n", server_url="https://x/sse", transport="sse", auth_type="NONE"
    )
    assert body.transport == "SSE"


def test_upsert_body_rejects_bad_auth_type():
    from models.mcp_admin import MCPServerUpsertBody

    with pytest.raises(ValidationError):
        MCPServerUpsertBody(name="n", server_url="https://x/mcp", auth_type="BOGUS")


def test_upsert_body_rejects_bad_auth_performer():
    from models.mcp_admin import MCPServerUpsertBody

    with pytest.raises(ValidationError):
        MCPServerUpsertBody(
            name="n", server_url="https://x/mcp", auth_type="OAUTH", auth_performer="NOBODY"
        )


def test_tool_status_body_requires_int_ids():
    from models.mcp_admin import ToolStatusBody

    body = ToolStatusBody(tool_ids=[1, 2, 3], enabled=False)
    assert body.tool_ids == [1, 2, 3]
    assert body.enabled is False


def test_oauth_connect_body_defaults():
    from models.mcp_admin import MCPOAuthConnectBody

    body = MCPOAuthConnectBody(server_id="1000")
    assert body.include_resource_param is False
    assert body.return_path is None


def test_create_body_minimal():
    from models.mcp_admin import MCPServerCreateBody

    body = MCPServerCreateBody(name="n", server_url="https://x/mcp")
    assert body.description is None
