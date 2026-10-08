"""Mail tool binding tests for dynamic graph construction.

The wrapper no longer forwards to the tools-service MCP tool: SMTP
credentials stay inside agent-service, which performs the send itself. The
raw tool is still what the wrapper stands in for, so these tests keep it in
the map and assert on what reached the mail service instead.
"""

from types import SimpleNamespace

import pytest
from langchain_core.tools import StructuredTool

from agents.graphs.builder import GraphBuilder


@pytest.mark.asyncio
async def test_graph_builder_wraps_send_email_with_selected_mail_config(monkeypatch):
    """Dynamic agents should inject SMTP config server-side for send_email."""
    captured = {}

    async def raw_send_email(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
        reply_to: str | None = None,
    ) -> str:
        raise AssertionError("the send must not be forwarded over MCP")

    raw_tool = StructuredTool.from_function(
        coroutine=raw_send_email,
        name="send_email",
        description="Raw MCP mail sender",
    )

    async def _send_email(user_id, config_id, payload, owner_user_id=None):
        captured.update(payload)
        captured["user_id"] = user_id
        captured["config_id"] = config_id
        return {"success": True, "message": "Email sent."}

    mail_service = SimpleNamespace(send_email=_send_email)
    monkeypatch.setattr(
        "service.auth.mail_config_service.get_mail_config_service",
        lambda: mail_service,
    )

    builder = GraphBuilder(mcp_tools_map={"send_email": raw_tool})
    tools = builder._get_tools_for_names(
        ["send_email"],
        tool_configs={"send_email": {"mail_config_id": "mail-config-1"}},
        user_id="user-1",
    )

    assert len(tools) == 1
    assert "smtp_config" not in tools[0].args

    result = await tools[0].ainvoke(
        {
            "to": ["recipient@example.com"],
            "subject": "Merhaba",
            "body": "Merhaba",
        }
    )

    assert result == "Email sent."
    assert "smtp_config" not in captured
    assert captured["user_id"] == "user-1"
    assert captured["config_id"] == "mail-config-1"
    assert captured["to"] == ["recipient@example.com"]


@pytest.mark.asyncio
async def test_graph_builder_resolves_selected_chat_attachments(monkeypatch):
    """send_email should pass only selected chat attachments to the raw MCP tool."""
    captured = {}

    async def raw_send_email(
        to: list[str],
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
        **kwargs: object,
    ) -> str:
        raise AssertionError("the send must not be forwarded over MCP")

    raw_tool = StructuredTool.from_function(
        coroutine=raw_send_email,
        name="send_email",
        description="Raw MCP mail sender",
    )

    async def _send_email(user_id, config_id, payload, owner_user_id=None):
        captured.update(payload)
        return {"success": True, "message": "Email sent."}

    mail_service = SimpleNamespace(send_email=_send_email)
    monkeypatch.setattr(
        "service.auth.mail_config_service.get_mail_config_service",
        lambda: mail_service,
    )

    builder = GraphBuilder(mcp_tools_map={"send_email": raw_tool})
    tools = builder._get_tools_for_names(
        ["send_email"],
        tool_configs={"send_email": {"mail_config_id": "mail-config-1"}},
        user_id="user-1",
        mail_attachments=[
            {
                "id": "file-1",
                "filename": "report.txt",
                "mime_type": "text/plain",
                "content_base64": "UmVwb3J0",
            }
        ],
    )

    assert "smtp_config" not in tools[0].args
    assert "attachments" in tools[0].args

    result = await tools[0].ainvoke(
        {
            "to": ["recipient@example.com"],
            "subject": "Report",
            "body": "Attached.",
            "attachments": ["report.txt"],
        }
    )

    assert result == "Email sent."
    assert captured["attachments"] == [
        {
            "filename": "report.txt",
            "mime_type": "text/plain",
            "content_base64": "UmVwb3J0",
        }
    ]
