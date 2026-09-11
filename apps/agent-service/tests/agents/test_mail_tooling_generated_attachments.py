"""Attaching documents produced mid-run by the document tools to send_email.

``mail_attachments`` only carries files the frontend uploaded with the chat
turn. Files produced during the same run by ``create_document`` /
``create_spreadsheet`` are persisted to the ``document`` table (scoped to the
thread), MinIO and the in-memory ``FileService`` cache — but never added to
``mail_attachments``. These tests pin that ``send_email`` resolves a requested
attachment name against those generated documents before declaring it
unavailable.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.tools import StructuredTool

from agents.mail_tooling import wrap_send_email_tool

SMTP_CONFIG = {
    "host": "smtp.example.com",
    "port": 587,
    "username": "agent@example.com",
    "password": "secret",
    "from_email": "agent@example.com",
    "security": "starttls",
}


def _raw_tool(captured: dict) -> StructuredTool:
    async def raw_send_email(
        smtp_config: dict,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
        reply_to: str | None = None,
        attachments: list[dict] | None = None,
    ) -> str:
        captured["attachments"] = attachments
        return "sent"

    return StructuredTool.from_function(
        coroutine=raw_send_email,
        name="send_email",
        description="Raw MCP mail sender",
    )


@pytest.fixture
def _mail_service(monkeypatch):
    service = SimpleNamespace(
        get_decrypted_config=AsyncMock(return_value=SMTP_CONFIG),
        get_effective_user_smtp_config=AsyncMock(return_value=SMTP_CONFIG),
    )
    monkeypatch.setattr(
        "service.MailConfigService.get_mail_config_service",
        lambda: service,
    )
    return service


@pytest.mark.asyncio
async def test_send_email_attaches_document_generated_earlier_in_thread(monkeypatch, _mail_service):
    """A file created by create_document this run is attachable by its name."""
    captured: dict = {}
    thread_id = "11111111-1111-1111-1111-111111111111"
    pdf_bytes = b"%PDF-1.7 generated report"

    repo = SimpleNamespace(
        list_by_thread=AsyncMock(
            return_value=[
                {
                    "file_id": "gen-file-1",
                    "filename": "rapor.pdf",
                    "mime_type": "application/pdf",
                    "minio_object_key": "user-1/gen-file-1/rapor.pdf",
                }
            ]
        )
    )
    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "service.FileService.get_file",
        lambda file_id: SimpleNamespace(data=pdf_bytes) if file_id == "gen-file-1" else None,
    )

    tool = wrap_send_email_tool(
        _raw_tool(captured),
        mail_config_id="mail-config-1",
        user_id="user-1",
        mail_attachments=[],
    )

    result = await tool.ainvoke(
        {
            "to": ["recipient@example.com"],
            "subject": "Rapor",
            "body": "Ekte.",
            "attachments": ["rapor.pdf"],
        },
        config={"configurable": {"thread_id": thread_id, "user_id": "user-1"}},
    )

    assert result == "sent"
    assert captured["attachments"] == [
        {
            "filename": "rapor.pdf",
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        }
    ]


@pytest.mark.asyncio
async def test_send_email_falls_back_to_minio_when_cache_evicted(monkeypatch, _mail_service):
    """When the in-memory cache has dropped the file, MinIO bytes are used."""
    captured: dict = {}
    thread_id = "22222222-2222-2222-2222-222222222222"
    xlsx_bytes = b"PK\x03\x04 generated sheet"

    repo = SimpleNamespace(
        list_by_thread=AsyncMock(
            return_value=[
                {
                    "file_id": "gen-file-2",
                    "filename": "veriler.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "minio_object_key": "user-1/gen-file-2/veriler.xlsx",
                }
            ]
        )
    )
    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )
    monkeypatch.setattr("service.FileService.get_file", lambda file_id: None)
    monkeypatch.setattr(
        "service.MinioService.download_file",
        lambda object_key: xlsx_bytes if object_key == "user-1/gen-file-2/veriler.xlsx" else b"",
    )

    tool = wrap_send_email_tool(
        _raw_tool(captured),
        mail_config_id="mail-config-1",
        user_id="user-1",
        mail_attachments=[],
    )

    result = await tool.ainvoke(
        {
            "to": ["recipient@example.com"],
            "subject": "Veriler",
            "body": "Ekte.",
            "attachments": ["veriler.xlsx"],
        },
        config={"configurable": {"thread_id": thread_id, "user_id": "user-1"}},
    )

    assert result == "sent"
    assert captured["attachments"][0]["content_base64"] == base64.b64encode(xlsx_bytes).decode(
        "ascii"
    )


@pytest.mark.asyncio
async def test_send_email_still_reports_truly_unknown_attachment(monkeypatch, _mail_service):
    """A name that is neither uploaded nor generated stays an error."""
    captured: dict = {}
    thread_id = "33333333-3333-3333-3333-333333333333"

    repo = SimpleNamespace(list_by_thread=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )

    tool = wrap_send_email_tool(
        _raw_tool(captured),
        mail_config_id="mail-config-1",
        user_id="user-1",
        mail_attachments=[],
    )

    result = await tool.ainvoke(
        {
            "to": ["recipient@example.com"],
            "subject": "Yok",
            "body": "Ekte.",
            "attachments": ["yok.pdf"],
        },
        config={"configurable": {"thread_id": thread_id, "user_id": "user-1"}},
    )

    assert "unavailable" in result
    assert "yok.pdf" in result
    assert captured == {}


@pytest.mark.asyncio
async def test_send_email_mixes_uploaded_and_generated_attachments(monkeypatch, _mail_service):
    """Uploaded files keep working alongside a generated one in the same call."""
    captured: dict = {}
    thread_id = "44444444-4444-4444-4444-444444444444"
    uploaded_b64 = base64.b64encode(b"uploaded contract").decode("ascii")
    gen_bytes = b"%PDF-1.7 summary"

    repo = SimpleNamespace(
        list_by_thread=AsyncMock(
            return_value=[
                {
                    "file_id": "gen-file-3",
                    "filename": "ozet.pdf",
                    "mime_type": "application/pdf",
                    "minio_object_key": "k",
                }
            ]
        )
    )
    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "service.FileService.get_file",
        lambda file_id: SimpleNamespace(data=gen_bytes) if file_id == "gen-file-3" else None,
    )

    tool = wrap_send_email_tool(
        _raw_tool(captured),
        mail_config_id="mail-config-1",
        user_id="user-1",
        mail_attachments=[
            {
                "filename": "sozlesme.pdf",
                "mime_type": "application/pdf",
                "content_base64": uploaded_b64,
            }
        ],
    )

    result = await tool.ainvoke(
        {
            "to": ["recipient@example.com"],
            "subject": "Belgeler",
            "body": "Ekte.",
            "attachments": ["sozlesme.pdf", "ozet.pdf"],
        },
        config={"configurable": {"thread_id": thread_id, "user_id": "user-1"}},
    )

    assert result == "sent"
    names = {a["filename"] for a in captured["attachments"]}
    assert names == {"sozlesme.pdf", "ozet.pdf"}
