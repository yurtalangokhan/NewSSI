"""Mail Tools Category.

Provides SMTP-backed email sending for configured agents.
"""

from __future__ import annotations

import base64
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

from i18n import t

from ..core.base import BaseToolCategory
from .response import error_response, success_response


def _as_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _attach_files(message: EmailMessage, attachments: list[dict[str, Any]] | None) -> None:
    for attachment in attachments or []:
        filename = str(attachment.get("filename") or "").strip()
        content_base64 = str(attachment.get("content_base64") or "").strip()
        mime_type = str(attachment.get("mime_type") or "application/octet-stream").split(";")[0]
        maintype, _, subtype = mime_type.partition("/")
        if not filename or not content_base64:
            raise ValueError("Attachment filename and content are required.")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        content = base64.b64decode(content_base64, validate=True)
        message.add_attachment(
            content,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )


def send_email_message(
    *,
    smtp_config: dict[str, Any],
    to: list[str] | str,
    cc: list[str] | str | None = None,
    bcc: list[str] | str | None = None,
    subject: str,
    body: str,
    is_html: bool = False,
    reply_to: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    """Send an email using a supplied SMTP configuration."""
    to_list = _as_list(to)
    cc_list = _as_list(cc)
    bcc_list = _as_list(bcc)
    all_recipients = [*to_list, *cc_list, *bcc_list]

    if not all_recipients or not subject.strip() or not body.strip():
        return error_response("mail.recipient_subject_body_required", error_category="validation")

    required_config = ("host", "port", "username", "password", "from_email")
    if any(not smtp_config.get(key) for key in required_config):
        return error_response("mail.config_incomplete", error_category="configuration")

    message = EmailMessage()
    from_email = str(smtp_config["from_email"])
    from_name = str(smtp_config.get("from_name") or "").strip()
    message["From"] = formataddr((from_name, from_email)) if from_name else from_email
    message["To"] = ", ".join(to_list)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if reply_to:
        message["Reply-To"] = reply_to
    message["Subject"] = subject.strip()
    message["Message-ID"] = make_msgid()

    if is_html:
        message.set_content("This email contains HTML content.")
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    try:
        _attach_files(message, attachments)
    except (ValueError, TypeError):
        return error_response("mail.payload_invalid", error_category="validation")

    host = str(smtp_config["host"])
    port = int(smtp_config["port"])
    username = str(smtp_config["username"])
    password = str(smtp_config["password"])
    security = str(smtp_config.get("security") or "starttls").lower()
    context = ssl.create_default_context()

    try:
        if security == "ssl":
            smtp_cls = smtplib.SMTP_SSL
            with smtp_cls(host, port, timeout=15, context=context) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                if security == "starttls":
                    smtp.starttls(context=context)
                smtp.login(username, password)
                smtp.send_message(message)
    except smtplib.SMTPAuthenticationError:
        return error_response("mail.auth_failed", error_category="authentication")
    except (TimeoutError, OSError, smtplib.SMTPConnectError):
        return error_response("mail.connection_failed", error_category="connection")
    except smtplib.SMTPRecipientsRefused:
        return error_response("mail.recipient_rejected", error_category="recipient")
    except smtplib.SMTPException:
        return error_response("mail.message_rejected", error_category="smtp")

    return success_response(
        {
            "message_id": message["Message-ID"],
            "recipient_count": len(all_recipients),
        }
    )


class MailTools(BaseToolCategory):
    """Email sending tools."""

    @property
    def name(self) -> str:
        return "mail"

    @property
    def description(self) -> str:
        return t("categories.mail.description", default="SMTP email sending")

    @property
    def label(self) -> str:
        return t("categories.mail.label", default="Mail")

    def register_tools(self, mcp: Any) -> None:
        """Register all mail tools with MCP."""

        @mcp.tool()
        def send_email(
            smtp_config: dict[str, Any],
            to: list[str],
            subject: str,
            body: str,
            cc: list[str] | None = None,
            bcc: list[str] | None = None,
            is_html: bool = False,
            reply_to: str | None = None,
            attachments: list[dict[str, Any]] | None = None,
        ) -> str:
            """
            Send an email through the platform-selected SMTP configuration.

            Use this tool only when the user asks to send an email or clearly
            authorizes sending one. Ask for missing recipient, subject, or
            message body before calling the tool. Do not ask the user for SMTP
            credentials; the platform supplies the selected SMTP configuration
            automatically. Summarize the send result after the tool returns.
            """
            return send_email_message(
                smtp_config=smtp_config,
                to=to,
                cc=cc,
                bcc=bcc,
                subject=subject,
                body=body,
                is_html=is_html,
                reply_to=reply_to,
                attachments=attachments,
            )
