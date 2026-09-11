from __future__ import annotations

import json
import smtplib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from i18n.core import set_locale

from service.MailConfigService import MailConfigService


@pytest.mark.asyncio
async def test_admin_lists_all_active_mail_configs_without_owner_filter():
    rows = [
        {"id": "config-1", "user_id": "admin-old", "password_encrypted": None},
        {"id": "config-2", "user_id": "admin-current", "password_encrypted": None},
    ]
    repo = SimpleNamespace(list_active=AsyncMock(return_value=rows))
    service = MailConfigService(repo=repo)

    result = await service.list_configs("admin-current")

    assert [config["id"] for config in result] == ["config-1", "config-2"]
    repo.list_active.assert_awaited_once_with(search=None, page=None, page_size=None)


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

    repo.has_active_bindings.assert_awaited_once_with("config-1")
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

    user_cred_repo = SimpleNamespace(get_by_user_id=AsyncMock(return_value=None))
    service = MailConfigService(repo=repo, user_cred_repo=user_cred_repo)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected_subject", "expected_body", "expected_message"),
    [
        (
            "en",
            "Agentic AI SMTP Verification",
            "This test email confirms that your personal SMTP credentials are valid and can send mail.",
            "Test email sent successfully!",
        ),
        (
            "tr",
            "Agentic AI SMTP Doğrulaması",
            "Bu test e-postası, kişisel SMTP bilgilerinizin geçerli olduğunu ve e-posta gönderebildiğini doğrular.",
            "Test e-postası başarıyla gönderildi!",
        ),
    ],
)
async def test_user_credentials_verification_email_uses_request_locale(
    monkeypatch,
    locale,
    expected_subject,
    expected_body,
    expected_message,
):
    captured = {}
    repo = SimpleNamespace(
        get_active_by_id=AsyncMock(
            return_value={
                "id": "config-1",
                "host": "smtp.example.com",
                "port": 587,
                "security": "starttls",
            }
        )
    )
    user_cred_repo = SimpleNamespace(
        get_by_user_id=AsyncMock(
            return_value={
                "mail_config_id": "config-1",
                "username": "sender@example.com",
                "password_encrypted": "encrypted",
                "from_email": "sender@example.com",
                "from_name": "Sender",
            }
        ),
        mark_tested=AsyncMock(),
    )

    def fake_send(_config, _recipient, subject, body):
        captured.update(subject=subject, body=body)
        return '{"success": true}'

    monkeypatch.setattr("service.MailConfigService.decrypt_secret", lambda _value: "secret")
    monkeypatch.setattr(MailConfigService, "_send_email_message", staticmethod(fake_send))
    service = MailConfigService(repo=repo, user_cred_repo=user_cred_repo)

    set_locale(locale)
    try:
        result = await service.test_user_credentials("user-1", "config-1")
    finally:
        set_locale("en")

    assert captured == {"subject": expected_subject, "body": expected_body}
    assert result["message"] == expected_message
    user_cred_repo.mark_tested.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected_subject", "expected_body"),
    [
        (
            "en",
            "Agentic AI SMTP test",
            "This test email confirms that your SMTP configuration can send mail.",
        ),
        (
            "tr",
            "Agentic AI SMTP Testi",
            "Bu test e-postası, SMTP yapılandırmanızın e-posta gönderebildiğini doğrular.",
        ),
    ],
)
async def test_admin_smtp_test_email_uses_request_locale(
    monkeypatch,
    locale,
    expected_subject,
    expected_body,
):
    captured = {}
    repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value={
                "host": "smtp.example.com",
                "port": 587,
                "username": "sender@example.com",
                "password_encrypted": "encrypted",
                "from_email": "sender@example.com",
                "security": "starttls",
            }
        ),
        mark_tested=AsyncMock(),
    )

    def fake_send(_config, _recipient, subject, body):
        captured.update(subject=subject, body=body)
        return '{"success": true}'

    monkeypatch.setattr("service.MailConfigService.decrypt_secret", lambda _value: "secret")
    monkeypatch.setattr(MailConfigService, "_send_email_message", staticmethod(fake_send))
    service = MailConfigService(repo=repo)

    set_locale(locale)
    try:
        result = await service.send_test_email(
            "user-1",
            "config-1",
            "recipient@example.com",
        )
    finally:
        set_locale("en")

    assert captured == {"subject": expected_subject, "body": expected_body}
    assert result["success"] is True
    repo.mark_tested.assert_awaited_once_with("config-1", status="success")


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


@pytest.mark.asyncio
async def test_mail_config_delete_blocks_active_agent_bindings_in_turkish():
    repo = SimpleNamespace(
        has_active_bindings=AsyncMock(return_value=True),
        deactivate=AsyncMock(),
    )
    service = MailConfigService(repo=repo)

    set_locale("tr")
    try:
        with pytest.raises(ValueError, match="temsilciye bağlı"):
            await service.delete_config("user-1", "config-1")
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


@pytest.mark.asyncio
async def test_send_test_email_marks_success_when_test_passes(monkeypatch):
    repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value={
                "id": "config-1",
                "user_id": "user-1",
                "name": "Work",
                "host": "smtp.example.com",
                "port": 587,
                "username": "sender@example.com",
                "password_encrypted": "encrypted",
                "from_email": "sender@example.com",
                "security": "starttls",
            }
        ),
        mark_tested=AsyncMock(),
    )
    monkeypatch.setattr("service.MailConfigService.decrypt_secret", lambda _v: "secret")
    monkeypatch.setattr(
        MailConfigService,
        "_send_email_message",
        staticmethod(lambda *args, **kwargs: '{"success": true}'),
    )

    service = MailConfigService(repo=repo)
    result = await service.send_test_email("user-1", "config-1", "recipient@example.com")

    assert result["success"] is True
    repo.mark_tested.assert_awaited_once_with("config-1", status="success")


@pytest.mark.asyncio
async def test_send_test_email_marks_failed_when_test_fails(monkeypatch):
    repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value={
                "id": "config-1",
                "user_id": "user-1",
                "name": "Work",
                "host": "smtp.example.com",
                "port": 587,
                "username": "sender@example.com",
                "password_encrypted": "encrypted",
                "from_email": "sender@example.com",
                "security": "starttls",
            }
        ),
        mark_tested=AsyncMock(),
    )
    monkeypatch.setattr("service.MailConfigService.decrypt_secret", lambda _v: "secret")
    monkeypatch.setattr(
        MailConfigService,
        "_send_email_message",
        staticmethod(
            lambda *args,
            **kwargs: '{"success": false, "error": "Connection refused", "error_category": "connection"}'
        ),
    )

    service = MailConfigService(repo=repo)
    result = await service.send_test_email("user-1", "config-1", "recipient@example.com")

    assert result["success"] is False
    repo.mark_tested.assert_awaited_once_with(
        "config-1", status="failed", error="Connection refused"
    )


@pytest.mark.asyncio
async def test_get_effective_user_smtp_config_merges_user_creds(monkeypatch):
    monkeypatch.setattr(
        "service.MailConfigService.decrypt_secret",
        lambda value: value.replace("encrypted:", ""),
    )

    base_repo = SimpleNamespace(get_active_by_id=AsyncMock())
    base_repo.get_active_by_id.return_value = {
        "id": "config-1",
        "user_id": "admin-1",
        "name": "Company SMTP",
        "host": "smtp.company.com",
        "port": 587,
        "username": None,
        "password_encrypted": None,
        "from_email": None,
        "from_name": None,
        "security": "starttls",
    }

    user_cred_repo = SimpleNamespace(get_by_user_id=AsyncMock())
    user_cred_repo.get_by_user_id.return_value = {
        "id": "cred-1",
        "user_id": "user-42",
        "mail_config_id": "config-1",
        "username": "jdoe@company.com",
        "password_encrypted": "encrypted:jdoesecret",
        "from_email": "jdoe@company.com",
        "from_name": "John Doe",
        "is_active": True,
    }

    service = MailConfigService(repo=base_repo, user_cred_repo=user_cred_repo)

    effective = await service.get_effective_user_smtp_config(
        user_id="user-42",
        mail_config_id="obsolete-agent-config",
        owner_user_id="admin-1",
    )

    assert effective["host"] == "smtp.company.com"
    assert effective["port"] == 587
    assert effective["security"] == "starttls"
    assert effective["username"] == "jdoe@company.com"
    assert effective["password"] == "jdoesecret"
    assert effective["from_email"] == "jdoe@company.com"
    assert effective["from_name"] == "John Doe"
    base_repo.get_active_by_id.assert_awaited_once_with("config-1")


@pytest.mark.asyncio
async def test_upsert_user_credentials_persists_valid_selected_mail_config(monkeypatch):
    monkeypatch.setattr("service.MailConfigService.encrypt_secret", lambda value: f"enc:{value}")
    base_repo = SimpleNamespace(
        get_active_by_id=AsyncMock(return_value={"id": "config-1", "is_active": True})
    )
    user_cred_repo = SimpleNamespace(
        get_by_user_id=AsyncMock(return_value=None),
        upsert=AsyncMock(
            return_value={
                "id": "cred-1",
                "user_id": "user-42",
                "mail_config_id": "config-1",
                "username": "sender@example.com",
                "password_encrypted": "enc:secret",
                "from_email": "sender@example.com",
                "from_name": None,
                "is_active": True,
            }
        ),
    )
    service = MailConfigService(repo=base_repo, user_cred_repo=user_cred_repo)

    result = await service.upsert_user_credentials(
        "user-42",
        {
            "mail_config_id": "config-1",
            "username": "sender@example.com",
            "password": "secret",
            "from_email": "sender@example.com",
        },
    )

    assert result["mail_config_id"] == "config-1"
    user_cred_repo.upsert.assert_awaited_once_with(
        user_id="user-42",
        mail_config_id="config-1",
        username="sender@example.com",
        password_encrypted="enc:secret",
        from_email="sender@example.com",
        from_name=None,
    )


@pytest.mark.asyncio
async def test_upsert_user_credentials_rejects_inactive_selected_mail_config():
    base_repo = SimpleNamespace(get_active_by_id=AsyncMock(return_value=None))
    service = MailConfigService(
        repo=base_repo,
        user_cred_repo=SimpleNamespace(get_by_user_id=AsyncMock(return_value=None)),
    )

    with pytest.raises(ValueError, match="mail configuration"):
        await service.upsert_user_credentials(
            "user-42",
            {
                "mail_config_id": "inactive-config",
                "username": "sender@example.com",
                "password": "secret",
                "from_email": "sender@example.com",
            },
        )


@pytest.mark.asyncio
async def test_get_effective_user_smtp_config_raises_when_no_creds():
    base_repo = SimpleNamespace(get_by_id=AsyncMock())
    base_repo.get_by_id.return_value = {
        "id": "config-1",
        "user_id": "admin-1",
        "name": "Company SMTP",
        "host": "smtp.company.com",
        "port": 587,
        "username": None,
        "password_encrypted": None,
        "from_email": None,
        "security": "starttls",
    }

    user_cred_repo = SimpleNamespace(get_by_user_id=AsyncMock(return_value=None))

    service = MailConfigService(repo=base_repo, user_cred_repo=user_cred_repo)

    with pytest.raises(ValueError, match="Please configure your email credentials"):
        await service.get_effective_user_smtp_config(
            user_id="user-42",
            mail_config_id="config-1",
            owner_user_id="admin-1",
        )
