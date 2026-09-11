"""Mail tool binding tests for dynamic graph construction."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.tools import StructuredTool

from agents.graphs.builder import GraphBuilder


@pytest.mark.asyncio
async def test_graph_builder_wraps_send_email_with_selected_mail_config(monkeypatch):
    """Dynamic agents should inject SMTP config server-side for send_email."""
    captured = {}

    async def raw_send_email(
        smtp_config: dict,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
        reply_to: str | None = None,
    ) -> str:
        captured["smtp_config"] = smtp_config
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["cc"] = cc
        captured["bcc"] = bcc
        captured["is_html"] = is_html
        captured["reply_to"] = reply_to
        return "sent"

    raw_tool = StructuredTool.from_function(
        coroutine=raw_send_email,
        name="send_email",
        description="Raw MCP mail sender",
    )

    mail_service = SimpleNamespace(
        get_effective_user_smtp_config=AsyncMock(
            return_value={
                "host": "smtp.example.com",
                "port": 587,
                "username": "agent@example.com",
                "password": "secret",
                "from_email": "agent@example.com",
                "security": "starttls",
            }
        )
    )
    monkeypatch.setattr(
        "service.MailConfigService.get_mail_config_service",
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

    assert result == "sent"
    assert captured["smtp_config"]["host"] == "smtp.example.com"
    mail_service.get_effective_user_smtp_config.assert_awaited_once_with(
        user_id="user-1",
        mail_config_id="mail-config-1",
        owner_user_id=None,
    )


@pytest.mark.asyncio
async def test_graph_builder_resolves_selected_chat_attachments(monkeypatch):
    """send_email should pass only selected chat attachments to the raw MCP tool."""
    captured = {}

    async def raw_send_email(
        smtp_config: dict,
        to: list[str],
        subject: str,
        body: str,
        attachments: list[dict] | None = None,
        **kwargs: object,
    ) -> str:
        _ = kwargs
        captured["smtp_config"] = smtp_config
        captured["attachments"] = attachments
        return "sent"

    raw_tool = StructuredTool.from_function(
        coroutine=raw_send_email,
        name="send_email",
        description="Raw MCP mail sender",
    )

    mail_service = SimpleNamespace(
        get_effective_user_smtp_config=AsyncMock(
            return_value={
                "host": "smtp.example.com",
                "port": 587,
                "username": "agent@example.com",
                "password": "secret",
                "from_email": "agent@example.com",
                "security": "starttls",
            }
        )
    )
    monkeypatch.setattr(
        "service.MailConfigService.get_mail_config_service",
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

    assert result == "sent"
    assert captured["attachments"] == [
        {
            "filename": "report.txt",
            "mime_type": "text/plain",
            "content_base64": "UmVwb3J0",
        }
    ]
