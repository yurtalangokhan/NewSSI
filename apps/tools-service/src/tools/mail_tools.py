"""Mail Tools Category.

Provides SMTP-backed email sending for configured agents.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import ipaddress
import smtplib
import socket
import ssl
from typing import Any

from localization import t

from ..core.base import BaseToolCategory
from ..core.schema import LongText, ShortText
from .response import error_response, success_response

# Per-attachment and whole-message ceilings. base64 payloads were decoded
# straight into memory with no bound, so one call could pin an arbitrary
# amount of the process's heap.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024

# Link-local carries the cloud metadata services. They are never a mail relay,
# so they stay blocked even when no allow-list is configured.
_METADATA_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)
_METADATA_HOSTNAMES = frozenset({"metadata.google.internal", "metadata.goog"})


def _allowed_smtp_hosts() -> frozenset[str]:
    """Hosts this deployment will connect to, pinned in code.

    Deliberately not environment-configurable: the SMTP egress allowlist is
    a security boundary, and a security boundary that a deployment can widen
    through configuration is one an attacker with env write access can
    disable. Empty means "not pinned".
    """
    return frozenset()


def _is_metadata_host(host: str) -> bool:
    if host.lower() in _METADATA_HOSTNAMES:
        return True
    candidates: list[str] = [host]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            candidates = [str(info[4][0]) for info in socket.getaddrinfo(host, None)]
        except OSError:
            # Unresolvable: the connection attempt will fail on its own, and
            # refusing here would block legitimate transient DNS failures.
            return False
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if any(address.version == network.version and address in network for network in _METADATA_NETWORKS):
            return True
    return False


def _reject_smtp_host(host: str) -> str | None:
    """Return an error payload when ``host`` must not be contacted."""
    allowed = _allowed_smtp_hosts()
    if allowed and host.lower() not in allowed:
        return error_response("mail.host_not_allowed", error_category="configuration")
    if _is_metadata_host(host):
        return error_response("mail.host_not_allowed", error_category="configuration")
    return None


def _as_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _attach_files(message: EmailMessage, attachments: list[dict[str, Any]] | None) -> None:
    total = 0
    for attachment in attachments or []:
        filename = str(attachment.get("filename") or "").strip()
        content_base64 = str(attachment.get("content_base64") or "").strip()
        mime_type = str(attachment.get("mime_type") or "application/octet-stream").split(";")[0]
        maintype, _, subtype = mime_type.partition("/")
        if not filename or not content_base64:
            raise ValueError("Attachment filename and content are required.")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        # Check the encoded length before decoding: base64 is ~4/3 of the
        # payload, so this refuses an oversized attachment without ever
        # materialising it.
        if len(content_base64) * 3 // 4 > MAX_ATTACHMENT_BYTES:
            raise ValueError("Attachment exceeds the per-file size limit.")
        content = base64.b64decode(content_base64, validate=True)
        total += len(content)
        if len(content) > MAX_ATTACHMENT_BYTES or total > MAX_TOTAL_ATTACHMENT_BYTES:
            raise ValueError("Attachments exceed the message size limit.")
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
    reply_to: ShortText | None = None,
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
    rejection = _reject_smtp_host(host)
    if rejection is not None:
        return rejection
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
        # The signature is the MCP tool schema: renaming or dropping args would
        # change the model-visible contract. The send itself is owned by
        # agent-service, so the args are intentionally unused here.
        def send_email(
            to: list[str],  # noqa: ARG001
            subject: ShortText,  # noqa: ARG001
            body: LongText,  # noqa: ARG001
            cc: list[str] | None = None,  # noqa: ARG001
            bcc: list[str] | None = None,  # noqa: ARG001
            is_html: bool = False,  # noqa: ARG001
            reply_to: ShortText | None = None,  # noqa: ARG001
            attachments: list[dict[str, Any]] | None = None,  # noqa: ARG001
        ) -> str:
            """
            Send an email through the platform-selected SMTP configuration.

            Use this tool only when the user asks to send an email or clearly
            authorizes sending one. Ask for missing recipient, subject, or
            message body before calling the tool. Do not ask the user for SMTP
            credentials; the platform supplies the selected SMTP configuration
            automatically. Summarize the send result after the tool returns.
            """
            # The tool stays registered so agents can still select it and the
            # platform wrapper can still match it by name, but it no longer
            # takes an smtp_config -- and therefore cannot dispatch anything.
            # agent-service owns the stored mail configuration and performs
            # the send itself (agents/mail_tooling.wrap_send_email_tool), so a
            # call arriving here came from something that bypassed the
            # platform path and must not be relayed.
            return error_response(
                "mail.config_incomplete",
                error_category="configuration",
            )
