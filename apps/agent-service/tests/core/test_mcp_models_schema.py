"""Schema-shape assertions for the external-MCP ORM models (plan task 1)."""

from __future__ import annotations

from core.db.models.mcp_oauth_session import MCPOAuthSessionModel
from core.db.models.mcp_provider import MCPProviderModel
from core.db.models.mcp_provider_auth import MCPProviderAuthModel
from core.db.models.mcp_tool import MCPToolModel


def test_mcp_provider_has_auth_columns():
    cols = set(MCPProviderModel.__table__.columns.keys())
    assert {
        "int_id",
        "auth_type",
        "auth_performer",
        "server_status",
        "auth_template",
        "owner_email",
        "oauth_metadata",
    } <= cols


def test_mcp_tool_has_enabled_and_int_id():
    cols = set(MCPToolModel.__table__.columns.keys())
    assert {"int_id", "enabled"} <= cols


def test_provider_auth_table_shape():
    cols = set(MCPProviderAuthModel.__table__.columns.keys())
    assert cols == {
        "id",
        "provider_id",
        "user_id",
        "credentials_encrypted",
        "oauth_access_token_encrypted",
        "oauth_refresh_token_encrypted",
        "oauth_expires_at",
        "oauth_scopes",
        "time_created",
        "time_updated",
    }
    assert MCPProviderAuthModel.__tablename__ == "mcp_provider_auth"


def test_oauth_session_table_shape():
    cols = set(MCPOAuthSessionModel.__table__.columns.keys())
    assert cols == {
        "state",
        "provider_id",
        "user_id",
        "code_verifier",
        "redirect_uri",
        "return_path",
        "client_id",
        "client_secret_encrypted",
        "token_url",
        "resource",
        "expires_at",
        "time_created",
    }
    assert list(MCPOAuthSessionModel.__table__.primary_key.columns.keys()) == ["state"]
