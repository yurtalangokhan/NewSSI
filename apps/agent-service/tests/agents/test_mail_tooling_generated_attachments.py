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

from agents.tooling.mail_tooling import wrap_send_email_tool

SMTP_CONFIG = {
    "host": "smtp.example.com",
    "port": 587,
    "username": "agent@example.com",
    "password": "secret",
    "from_email": "agent@example.com",
    "security": "starttls",
}


def _raw_tool(_captured: dict) -> StructuredTool:
    """The MCP tool the wrapper stands in for.

    It is never invoked any more -- agent-service sends the mail itself so
    SMTP credentials never cross the service boundary -- so this fails loudly
    if the wrapper ever forwards to it again. The resolved attachments are
    observed on the mail service instead (see the ``_mail_service`` fixture).
    """

    async def raw_send_email(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
        reply_to: str | None = None,
        attachments: list[dict] | None = None,
    ) -> str:
        raise AssertionError("the send must not be forwarded over MCP")

    return StructuredTool.from_function(
        coroutine=raw_send_email,
        name="send_email",
        description="Raw MCP mail sender",
    )


#: What the wrapper handed to the mail service on the last send. The tests
#: read the resolved attachments from here now that nothing goes over MCP.
_CAPTURED: dict = {}


@pytest.fixture
def _mail_service(monkeypatch):
    _CAPTURED.clear()

    async def _send_email(user_id, config_id, payload, owner_user_id=None):
        _CAPTURED.update(payload)
        return {"success": True, "message": "Email sent."}

    service = SimpleNamespace(
        get_decrypted_config=AsyncMock(return_value=SMTP_CONFIG),
        get_effective_user_smtp_config=AsyncMock(return_value=SMTP_CONFIG),
        send_email=_send_email,
    )
    monkeypatch.setattr(
        "service.auth.mail_config_service.get_mail_config_service",
        lambda: service,
    )
    return service


@pytest.mark.asyncio
async def test_send_email_attaches_document_generated_earlier_in_thread(monkeypatch, _mail_service):
    """A file created by create_document this run is attachable by its name."""
    captured = _CAPTURED
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
        "infrastructure.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "service.storage.file_service.get_file",
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

    assert result == "Email sent."
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
    captured = _CAPTURED
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
        "infrastructure.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )
    monkeypatch.setattr("service.storage.file_service.get_file", lambda file_id: None)
    monkeypatch.setattr(
        "service.storage.minio_service.download_file",
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

    assert result == "Email sent."
    assert captured["attachments"][0]["content_base64"] == base64.b64encode(xlsx_bytes).decode(
        "ascii"
    )


@pytest.mark.asyncio
async def test_send_email_still_reports_truly_unknown_attachment(monkeypatch, _mail_service):
    """A name that is neither uploaded nor generated stays an error."""
    captured = _CAPTURED
    thread_id = "33333333-3333-3333-3333-333333333333"

    repo = SimpleNamespace(list_by_thread=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "infrastructure.db.repositories.document_repo.DocumentRepository",
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
    captured = _CAPTURED
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
        "infrastructure.db.repositories.document_repo.DocumentRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "service.storage.file_service.get_file",
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

    assert result == "Email sent."
    names = {a["filename"] for a in captured["attachments"]}
    assert names == {"sozlesme.pdf", "ozet.pdf"}
