from __future__ import annotations

import json
import smtplib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from i18n.core import set_locale

from service.MailConfigService import MailConfigService


@pytest.mark.asyncio
async def test_mail_config_response_masks_secret(monkeypatch):
    monkeypatch.setattr(
        "service.MailConfigService.encrypt_secret",
        lambda value: f"encrypted:{value}",
    )

    repo = SimpleNamespace(create=AsyncMock())
    repo.create.return_value = {
        "id": "config-1",
        "user_id": "user-1",
        "name": "Support",
        "host": "smtp.example.com",
        "port": 587,
        "username": "support@example.com",
        "password_encrypted": "encrypted:secret",
        "from_email": "support@example.com",
        "from_name": "Support",
        "security": "starttls",
        "is_active": True,
        "last_tested_at": None,
        "time_created": "2026-08-03T10:00:00+00:00",
        "time_updated": "2026-08-03T10:00:00+00:00",
    }
    service = MailConfigService(repo=repo)

    result = await service.create_config(
        user_id="user-1",
        payload={
            "name": "Support",
            "host": "smtp.example.com",
            "port": 587,
            "username": "support@example.com",
            "password": "secret",
            "from_email": "support@example.com",
            "from_name": "Support",
            "security": "starttls",
        },
    )

    assert result["password_configured"] is True
    assert "password" not in result
    assert "password_encrypted" not in result
    repo.create.assert_awaited_once()
    assert repo.create.await_args.kwargs["password_encrypted"] == "encrypted:secret"


@pytest.mark.asyncio
async def test_mail_config_delete_blocks_active_agent_bindings():
    repo = SimpleNamespace(
        has_active_bindings=AsyncMock(return_value=True),
        deactivate=AsyncMock(),
    )
    service = MailConfigService(repo=repo)

    with pytest.raises(ValueError, match="attached to an agent"):
        await service.delete_config("user-1", "config-1")

    repo.deactivate.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_email_uses_selected_mail_config(monkeypatch):
    captured = {}

    repo = SimpleNamespace(get_by_id=AsyncMock())
    repo.get_by_id.return_value = {
        "id": "config-1",
        "user_id": "user-1",
        "name": "Work",
        "host": "smtp.example.com",
        "port": 587,
        "username": "sender@example.com",
        "password_encrypted": "encrypted",
        "from_email": "sender@example.com",
        "from_name": "Sender",
        "security": "starttls",
    }

    def fake_send(config, payload):
        captured["config"] = config
        captured["payload"] = payload
        return '{"success": true, "message_id": "msg-1"}'

    monkeypatch.setattr("service.MailConfigService.decrypt_secret", lambda _value: "secret")
    monkeypatch.setattr(MailConfigService, "_send_email_payload", staticmethod(fake_send))

    service = MailConfigService(repo=repo)
    result = await service.send_email(
        "user-1",
        "config-1",
        {
            "to": ["recipient@example.com"],
            "subject": "Merhaba",
            "body": "Merhaba",
            "cc": [],
            "bcc": [],
            "is_html": False,
            "reply_to": None,
        },
    )

    assert result["success"] is True
    assert result["message"] == "Email sent."
    assert captured["config"]["password"] == "secret"
    assert captured["payload"]["subject"] == "Merhaba"


def test_mail_config_test_email_reports_connection_timeout(monkeypatch):
    class TimeoutSMTP:
        def __init__(self, *_args, **_kwargs):
            raise TimeoutError("timed out")

    monkeypatch.setattr("service.MailConfigService.smtplib.SMTP", TimeoutSMTP)

    result = MailConfigService._send_email_message(
        {
            "host": "smtp.mailersend.net",
            "port": 587,
            "username": "smtp-user",
            "password": "secret",
            "from_email": "sender@example.com",
            "security": "starttls",
        },
        "sender@example.com",
        "Diagnostic",
        "Body",
    )

    payload = json.loads(result)
    assert payload["success"] is False
    assert payload["error_category"] == "connection"
    assert "could not be reached" in payload["error"]


def test_mail_config_test_email_reports_connection_timeout_in_turkish(monkeypatch):
    class TimeoutSMTP:
        def __init__(self, *_args, **_kwargs):
            raise TimeoutError("timed out")

    monkeypatch.setattr("service.MailConfigService.smtplib.SMTP", TimeoutSMTP)

    set_locale("tr")
    try:
        result = MailConfigService._send_email_message(
            {
                "host": "smtp.mailersend.net",
                "port": 587,
                "username": "smtp-user",
                "password": "secret",
                "from_email": "sender@example.com",
                "security": "starttls",
            },
            "sender@example.com",
            "Diagnostic",
            "Body",
        )
    finally:
        set_locale("en")

    payload = json.loads(result)
    assert payload["success"] is False
    assert payload["error"] == "SMTP sunucusuna ulaşılamadı: timed out"


def test_mail_config_delete_blocks_active_agent_bindings_in_turkish():
    repo = SimpleNamespace(
        has_active_bindings=AsyncMock(return_value=True),
        deactivate=AsyncMock(),
    )
    service = MailConfigService(repo=repo)

    set_locale("tr")
    try:
        with pytest.raises(ValueError, match="temsilciye bağlı"):
            import asyncio

            asyncio.get_event_loop().run_until_complete(service.delete_config("user-1", "config-1"))
    finally:
        set_locale("en")


class TestSmtpAuthenticationErrorIsTranslatedByExceptionType:
    """Mirrors the Keycloak invalid_grant fix: match on the exception TYPE
    (smtplib.SMTPAuthenticationError), translate the static wrapper text, and
    keep the SMTP server's own dynamic response text (which we cannot
    pre-translate) appended untranslated.
    """

    def test_send_email_payload_translates_auth_failure_wrapper(self, monkeypatch):
        class AuthFailSMTP:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def starttls(self, *_args, **_kwargs):
                return None

            def login(self, *_args, **_kwargs):
                raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

        monkeypatch.setattr("service.MailConfigService.smtplib.SMTP", AuthFailSMTP)
        monkeypatch.setattr(
            "service.MailConfigService.ssl.create_default_context", lambda: "context"
        )

        set_locale("tr")
        try:
            result = MailConfigService._send_email_payload(
                {
                    "host": "smtp.example.com",
                    "port": 587,
                    "username": "sender@example.com",
                    "password": "wrong-secret",
                    "from_email": "sender@example.com",
                    "security": "starttls",
                },
                {
                    "to": ["recipient@example.com"],
                    "subject": "Report",
                    "body": "Body",
                },
            )
        finally:
            set_locale("en")

        payload = json.loads(result)
        assert payload["success"] is False
        assert payload["error"] == "SMTP kimlik doğrulaması başarısız oldu: Authentication failed"


def test_send_email_payload_attaches_base64_files(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self, *_args, **_kwargs):
            return None

        def login(self, *_args, **_kwargs):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("service.MailConfigService.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("service.MailConfigService.ssl.create_default_context", lambda: "context")

    result = MailConfigService._send_email_payload(
        {
            "host": "smtp.example.com",
            "port": 587,
            "username": "sender@example.com",
            "password": "secret",
            "from_email": "sender@example.com",
            "security": "starttls",
        },
        {
            "to": ["recipient@example.com"],
            "subject": "Report",
            "body": "Attached.",
            "attachments": [
                {
                    "filename": "report.txt",
                    "mime_type": "text/plain",
                    "content_base64": "UmVwb3J0",
                }
            ],
        },
    )

    payload = json.loads(result)
    assert payload["success"] is True
    attachments = list(sent_messages[0].iter_attachments())
    assert attachments[0].get_filename() == "report.txt"
    assert attachments[0].get_payload(decode=True) == b"Report"
