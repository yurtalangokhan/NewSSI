"""`send_email` must not become an open relay or an unbounded memory sink.

The tool takes the SMTP endpoint as an argument. On the normal agent path
agent-service hides that argument and fills it from the stored mail config,
but nothing in tools-service itself constrained the host — so a principal
reaching the MCP endpoint directly could point the platform's mailer at any
server (relaying mail as the tenant, or harvesting whatever it is handed),
and attachments were base64-decoded with no size ceiling at all.
"""

from __future__ import annotations

import base64
import json

import pytest

from src.tools import mail_tools

BASE = {
    "to": ["someone@example.com"],
    "subject": "hi",
    "body": "hello",
}


def _config(host: str = "smtp.example.com") -> dict:
    return {
        "host": host,
        "port": 587,
        "username": "u",
        "password": "p",
        "from_email": "agent@example.com",
    }


def _sent(monkeypatch) -> list[str]:
    """Record the hosts an SMTP connection was actually attempted against."""
    hosts: list[str] = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            hosts.append(host)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            return None

        def login(self, username, password):
            return None

        def send_message(self, message):
            return None

    monkeypatch.setattr(mail_tools.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(mail_tools.smtplib, "SMTP_SSL", _FakeSMTP)
    return hosts


def test_an_unlisted_host_is_refused(monkeypatch):
    monkeypatch.setattr(mail_tools, "_allowed_smtp_hosts", lambda: frozenset({"smtp.corp.test"}))
    hosts = _sent(monkeypatch)

    result = json.loads(mail_tools.send_email_message(smtp_config=_config(), **BASE))

    assert result["success"] is False
    assert result["error_category"] == "configuration"
    assert hosts == [], "a connection was opened to a host that is not allow-listed"


def test_an_allow_listed_host_still_sends(monkeypatch):
    monkeypatch.setattr(mail_tools, "_allowed_smtp_hosts", lambda: frozenset({"smtp.example.com"}))
    hosts = _sent(monkeypatch)

    result = json.loads(mail_tools.send_email_message(smtp_config=_config(), **BASE))

    assert result["success"] is True
    assert hosts == ["smtp.example.com"]


def test_an_empty_allow_list_does_not_restrict_ordinary_hosts(monkeypatch):
    """Deployments that have not pinned their relay keep working."""
    monkeypatch.setattr(mail_tools, "_allowed_smtp_hosts", lambda: frozenset())
    hosts = _sent(monkeypatch)

    result = json.loads(mail_tools.send_email_message(smtp_config=_config(), **BASE))

    assert result["success"] is True
    assert hosts == ["smtp.example.com"]


@pytest.mark.parametrize(
    "host",
    ["169.254.169.254", "metadata.google.internal", "169.254.170.2"],
)
def test_metadata_endpoints_are_refused_even_with_an_empty_allow_list(monkeypatch, host):
    """No allow-list is not permission to talk to the instance metadata service."""
    monkeypatch.setattr(mail_tools, "_allowed_smtp_hosts", lambda: frozenset())
    hosts = _sent(monkeypatch)

    result = json.loads(mail_tools.send_email_message(smtp_config=_config(host), **BASE))

    assert result["success"] is False
    assert hosts == []


def test_oversized_attachments_are_refused(monkeypatch):
    monkeypatch.setattr(mail_tools, "_allowed_smtp_hosts", lambda: frozenset())
    hosts = _sent(monkeypatch)
    oversized = base64.b64encode(b"x" * (mail_tools.MAX_ATTACHMENT_BYTES + 1)).decode()

    result = json.loads(
        mail_tools.send_email_message(
            smtp_config=_config(),
            attachments=[{"filename": "big.bin", "content_base64": oversized}],
            **BASE,
        )
    )

    assert result["success"] is False
    assert result["error_category"] == "validation"
    assert hosts == []


def test_many_small_attachments_cannot_exceed_the_total_ceiling(monkeypatch):
    monkeypatch.setattr(mail_tools, "_allowed_smtp_hosts", lambda: frozenset())
    hosts = _sent(monkeypatch)
    chunk = base64.b64encode(b"x" * (mail_tools.MAX_ATTACHMENT_BYTES // 2)).decode()

    result = json.loads(
        mail_tools.send_email_message(
            smtp_config=_config(),
            attachments=[
                {"filename": f"part{i}.bin", "content_base64": chunk}
                for i in range(
                    2 * mail_tools.MAX_TOTAL_ATTACHMENT_BYTES // mail_tools.MAX_ATTACHMENT_BYTES + 2
                )
            ],
            **BASE,
        )
    )

    assert result["success"] is False
    assert hosts == []
