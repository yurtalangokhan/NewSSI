from __future__ import annotations

import json

from i18n.core import set_locale

from src.tools.mail_tools import send_email_message


class FakeSMTP:
    instances: list[FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: int = 15, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.started_tls = False
        self.logged_in = None
        self.sent_message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def starttls(self, context=None):
        self.started_tls = True
        self.context = context

    def login(self, username: str, password: str):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.sent_message = message
        return {}


def test_send_email_message_uses_starttls_and_masks_secret(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr("src.tools.mail_tools.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("src.tools.mail_tools.ssl.create_default_context", lambda: "context")

    result = json.loads(
        send_email_message(
            smtp_config={
                "host": "smtp.example.com",
                "port": 587,
                "username": "sender@example.com",
                "password": "super-secret",
                "from_email": "sender@example.com",
                "from_name": "Sender",
                "security": "starttls",
            },
            to=["recipient@example.com"],
            cc=[],
            bcc=[],
            subject="Hello",
            body="Message body",
            is_html=False,
            reply_to=None,
        )
    )

    assert result["success"] is True
    assert result["recipient_count"] == 1
    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls is True
    assert smtp.logged_in == ("sender@example.com", "super-secret")
    assert smtp.sent_message["Subject"] == "Hello"
    assert "super-secret" not in json.dumps(result)


def test_send_email_message_rejects_missing_required_fields():
    result = json.loads(
        send_email_message(
            smtp_config={},
            to=[],
            cc=[],
            bcc=[],
            subject="",
            body="",
            is_html=False,
            reply_to=None,
        )
    )

    assert result["success"] is False
    assert result["error_category"] == "validation"
    assert result["error"] == "Recipient, subject, and body are required before sending email."


def test_send_email_message_error_is_translated_for_turkish_locale():
    set_locale("tr")
    try:
        result = json.loads(
            send_email_message(
                smtp_config={},
                to=[],
                cc=[],
                bcc=[],
                subject="",
                body="",
                is_html=False,
                reply_to=None,
            )
        )
    finally:
        set_locale("en")

    assert result["success"] is False
    assert result["error"] == "E-posta göndermeden önce alıcı, konu ve gövde gereklidir."


def test_mail_error_response_helper_shape_is_stable():
    """Snapshot: the consolidated error helper keeps the MCP-visible shape."""
    from src.tools.response import error_response

    output = json.loads(error_response("mail.auth_failed", error_category="authentication"))
    assert output == {
        "success": False,
        "error_category": "authentication",
        "error": "SMTP authentication failed.",
    }

    output_no_category = json.loads(error_response("mail.auth_failed"))
    assert output_no_category == {
        "success": False,
        "error": "SMTP authentication failed.",
    }


def test_send_email_message_validation_error_shape_is_stable():
    """Snapshot: validation/config errors keep error_category in the output."""
    result = json.loads(
        send_email_message(
            smtp_config={},
            to=[],
            cc=[],
            bcc=[],
            subject="",
            body="",
            is_html=False,
            reply_to=None,
        )
    )
    assert result == {
        "success": False,
        "error_category": "validation",
        "error": "Recipient, subject, and body are required before sending email.",
    }

    config_result = json.loads(
        send_email_message(
            smtp_config={"host": "x"},
            to=["a@example.com"],
            cc=[],
            bcc=[],
            subject="s",
            body="b",
            is_html=False,
            reply_to=None,
        )
    )
    assert config_result == {
        "success": False,
        "error_category": "configuration",
        "error": "SMTP configuration is incomplete.",
    }


def test_send_email_message_attaches_base64_files(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr("src.tools.mail_tools.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("src.tools.mail_tools.ssl.create_default_context", lambda: "context")

    result = json.loads(
        send_email_message(
            smtp_config={
                "host": "smtp.example.com",
                "port": 587,
                "username": "sender@example.com",
                "password": "super-secret",
                "from_email": "sender@example.com",
                "security": "starttls",
            },
            to=["recipient@example.com"],
            subject="With attachment",
            body="Please see attached.",
            attachments=[
                {
                    "filename": "hello.txt",
                    "mime_type": "text/plain",
                    "content_base64": "SGVsbG8=",
                }
            ],
        )
    )

    assert result["success"] is True
    smtp = FakeSMTP.instances[0]
    attachments = list(smtp.sent_message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "hello.txt"
    assert attachments[0].get_content_type() == "text/plain"
    assert attachments[0].get_payload(decode=True) == b"Hello"
