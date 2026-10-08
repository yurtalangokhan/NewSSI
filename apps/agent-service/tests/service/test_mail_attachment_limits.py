"""Attachments are bounded before they are decoded into the message.

`_attach_files` base64-decoded whatever it was handed, with no ceiling on
a single attachment or on the message as a whole, and swallowed a decode
failure with a bare `except: continue` -- so a malformed attachment was
silently dropped from a mail the user was told had been sent. The limits
used to live in tools-service, which no longer sees this payload now that
the send happens here.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage

from error_contract import BadRequestError, PayloadTooLargeError
import pytest

from tests.error_support import raises_localized
from service.auth.mail_config_service import (
    MAX_ATTACHMENT_BYTES,
    MAX_TOTAL_ATTACHMENT_BYTES,
    MailConfigService,
)


def _attachment(size: int, name: str = "file.bin") -> dict[str, str]:
    return {
        "filename": name,
        "mime_type": "application/octet-stream",
        "content_base64": base64.b64encode(b"x" * size).decode(),
    }


def test_a_normal_attachment_is_added():
    message = EmailMessage()
    message.set_content("body")

    MailConfigService._attach_files(message, [_attachment(64)])

    assert [part.get_filename() for part in message.iter_attachments()] == ["file.bin"]


def test_an_oversized_attachment_is_refused():
    message = EmailMessage()
    message.set_content("body")

    with raises_localized(PayloadTooLargeError, "size limit"):
        MailConfigService._attach_files(message, [_attachment(MAX_ATTACHMENT_BYTES + 1)])


def test_many_attachments_cannot_exceed_the_message_limit():
    message = EmailMessage()
    message.set_content("body")
    each = MAX_ATTACHMENT_BYTES
    count = (MAX_TOTAL_ATTACHMENT_BYTES // each) + 1

    with raises_localized(PayloadTooLargeError, "size limit"):
        MailConfigService._attach_files(
            message, [_attachment(each, f"f{i}.bin") for i in range(count)]
        )


def test_an_undecodable_attachment_is_an_error_not_a_silent_drop():
    message = EmailMessage()
    message.set_content("body")

    with pytest.raises(BadRequestError):
        MailConfigService._attach_files(
            message,
            [{"filename": "x.bin", "mime_type": "text/plain", "content_base64": "!!!!"}],
        )


def test_a_send_with_an_oversized_attachment_is_refused_not_silently_trimmed():
    with pytest.raises(PayloadTooLargeError):
        MailConfigService._send_email_payload(
            {"host": "smtp.example.com", "port": 587, "username": "u", "password": "p"},
            {
                "to": ["a@example.com"],
                "subject": "s",
                "body": "b",
                "attachments": [_attachment(MAX_ATTACHMENT_BYTES + 1)],
            },
        )
