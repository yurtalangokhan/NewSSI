"""Helpers for binding platform-managed SMTP configs to mail MCP tools."""

from __future__ import annotations

import base64
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from core.logger import get_logger

logger = get_logger(__name__)

EMAIL_TOOL_POLICY = (
    "Email sending policy:\n"
    "- You can send email with the send_email tool through the platform-selected mail "
    "configuration.\n"
    "- Before sending, ensure the recipient, subject, and message body are clear.\n"
    "- If any required field is missing, ask the user for it.\n"
    "- Call send_email with only these arguments: to, subject, body, and optional cc, "
    "bcc, is_html, reply_to, attachments.\n"
    "- When the user asks to attach a file from the current chat, set attachments to "
    "the exact file name or names listed in the available email attachments section.\n"
    "- You can also attach a document you created earlier in this conversation with "
    "create_document or create_spreadsheet by passing its exact file name.\n"
    "- Do not invent attachment names. If the requested file is neither listed nor one "
    "you generated in this conversation, ask the user to attach it to the chat first.\n"
    "- Never pass or ask for smtp_config, host, port, username, password, from_email, "
    "or mail configuration IDs; the platform injects them automatically.\n"
    "- Do not ask for SMTP credentials or mention internal mail configuration IDs.\n"
    "- After sending, summarize whether the email was sent."
)


class SendEmailInput(BaseModel):
    """LLM-safe schema for sending email."""

    to: list[str] = Field(description="Recipient email addresses.")
    subject: str = Field(description="Email subject.")
    body: str = Field(description="Email body.")
    cc: list[str] = Field(default_factory=list, description="CC recipient email addresses.")
    bcc: list[str] = Field(default_factory=list, description="BCC recipient email addresses.")
    is_html: bool = Field(default=False, description="Whether body contains HTML.")
    reply_to: str | None = Field(default=None, description="Optional reply-to email address.")
    attachments: list[str] = Field(
        default_factory=list,
        description="Exact file names from the current chat to attach to the email.",
    )


def _attachment_prompt(mail_attachments: list[dict[str, Any]] | None) -> str:
    names = [
        str(item.get("filename") or item.get("name") or "").strip()
        for item in mail_attachments or []
    ]
    names = [name for name in names if name]
    if not names:
        return ""
    lines = "\n".join(f"- {name}" for name in names)
    return f"\nAvailable email attachments from this chat:\n{lines}"


def append_email_tool_policy(
    system_prompt: str,
    tool_names: list[str],
    *,
    mail_attachments: list[dict[str, Any]] | None = None,
) -> str:
    """Append the mail policy only when the send_email tool is enabled."""
    if "send_email" not in tool_names:
        return system_prompt
    prompt = system_prompt
    if EMAIL_TOOL_POLICY not in prompt:
        prompt = f"{prompt}\n{EMAIL_TOOL_POLICY}"
    attachment_section = _attachment_prompt(mail_attachments)
    if attachment_section and "Available email attachments from this chat:" not in prompt:
        prompt = f"{prompt}{attachment_section}"
    return prompt


def _resolve_attachments(
    requested_attachments: list[str] | None,
    available_attachments: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Match requested names against chat-uploaded files.

    Returns ``(resolved, missing)`` — the attachment payloads that matched and
    the names that did not. Unmatched names are resolved against documents
    generated earlier in the thread by :func:`_resolve_generated_attachments`
    before the caller treats them as an error.
    """
    if not requested_attachments:
        return [], []

    by_name = {
        str(item.get("filename") or item.get("name") or "").strip(): item
        for item in available_attachments or []
    }
    resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in requested_attachments:
        key = str(name or "").strip()
        item = by_name.get(key)
        if not item:
            missing.append(key)
            continue
        resolved.append(
            {
                "filename": str(item.get("filename") or item.get("name") or key),
                "mime_type": str(item.get("mime_type") or "application/octet-stream"),
                "content_base64": str(item.get("content_base64") or item.get("data") or ""),
            }
        )

    return resolved, missing


def _load_generated_bytes(doc: dict[str, Any]) -> bytes | None:
    """Fetch a generated document's bytes, cache first then MinIO."""
    file_id = str(doc.get("file_id") or "").strip()
    if file_id:
        try:
            from service.FileService import get_file

            record = get_file(file_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("FileService lookup failed for %s: %s", file_id, exc)
            record = None
        if record is not None and getattr(record, "data", None):
            return record.data

    object_key = str(doc.get("minio_object_key") or "").strip()
    if object_key:
        try:
            from service.MinioService import download_file

            return download_file(object_key)
        except Exception as exc:
            logger.warning(
                "Could not load generated attachment from MinIO (%s): %s", object_key, exc
            )

    return None


async def _resolve_generated_attachments(
    names: list[str],
    *,
    thread_id: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Match names against documents produced earlier in this thread.

    ``mail_attachments`` only carries files the frontend uploaded with the
    turn; files the agent just built with create_document / create_spreadsheet
    live in the ``document`` table (scoped to the thread) plus the FileService
    cache and MinIO. Returns ``(resolved, still_missing)``.
    """
    if not names:
        return [], []
    if not thread_id:
        return [], list(names)

    try:
        from service.persistence_gateway import document_repository

        docs = await document_repository().list_by_thread(thread_id)
    except Exception as exc:
        logger.warning("Could not list thread documents for mail attachments: %s", exc)
        return [], list(names)

    # list_by_thread is ordered oldest-first; last write of a name wins.
    by_name: dict[str, dict[str, Any]] = {}
    for doc in docs or []:
        filename = str(doc.get("filename") or "").strip()
        if filename:
            by_name[filename] = doc

    resolved: list[dict[str, Any]] = []
    still_missing: list[str] = []
    for name in names:
        key = str(name or "").strip()
        doc = by_name.get(key)
        data = _load_generated_bytes(doc) if doc else None
        if data is None:
            still_missing.append(key)
            continue
        resolved.append(
            {
                "filename": key,
                "mime_type": str(doc.get("mime_type") or "application/octet-stream"),
                "content_base64": base64.b64encode(data).decode("ascii"),
            }
        )

    return resolved, still_missing


def wrap_send_email_tool(
    tool: BaseTool,
    *,
    mail_config_id: str | None,
    user_id: str | None,
    owner_user_id: str | None = None,
    mail_attachments: list[dict[str, Any]] | None = None,
) -> BaseTool:
    """Hide SMTP config from the LLM and inject effective user SMTP config at runtime."""

    async def send_email(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
        reply_to: str | None = None,
        attachments: list[str] | None = None,
        config: RunnableConfig = None,  # injected by LangChain, not exposed to the LLM
    ) -> str:
        if not mail_config_id or not user_id:
            return (
                "Email could not be sent because this agent does not have a valid "
                "mail configuration."
            )

        from service.MailConfigService import get_mail_config_service

        try:
            smtp_config = await get_mail_config_service().get_effective_user_smtp_config(
                user_id=user_id,
                mail_config_id=mail_config_id,
                owner_user_id=owner_user_id,
            )
        except ValueError as exc:
            return f"Email could not be sent: {exc}"
        except Exception:
            return "Email could not be sent because the configured mail account is unavailable."

        resolved_attachments, missing = _resolve_attachments(attachments, mail_attachments)
        if missing:
            thread_id = (config or {}).get("configurable", {}).get("thread_id")
            generated, still_missing = await _resolve_generated_attachments(
                missing,
                thread_id=str(thread_id) if thread_id else None,
            )
            resolved_attachments.extend(generated)
            if still_missing:
                return (
                    "Email could not be sent because these attachments are unavailable: "
                    f"{', '.join(still_missing)}."
                )

        return await tool.ainvoke(
            {
                "smtp_config": smtp_config,
                "to": to,
                "cc": cc or [],
                "bcc": bcc or [],
                "subject": subject,
                "body": body,
                "is_html": is_html,
                "reply_to": reply_to,
                "attachments": resolved_attachments,
            }
        )

    return StructuredTool.from_function(
        coroutine=send_email,
        name="send_email",
        description=(
            "Send an email through the platform-selected mail configuration. "
            "Use only after recipient, subject, and body are clear. Do not ask "
            "for SMTP credentials."
        ),
        args_schema=SendEmailInput,
    )


def maybe_wrap_mcp_tool(
    *,
    tool_name: str,
    tool: BaseTool,
    tool_configs: dict[str, Any] | None,
    user_id: str | None,
    owner_user_id: str | None = None,
    mail_attachments: list[dict[str, Any]] | None = None,
) -> BaseTool:
    """Apply server-side wrappers for MCP tools that need platform-managed config."""
    if tool_name != "send_email":
        return tool
    send_email_config = (tool_configs or {}).get("send_email") or {}
    return wrap_send_email_tool(
        tool,
        mail_config_id=send_email_config.get("mail_config_id"),
        user_id=user_id,
        owner_user_id=owner_user_id,
        mail_attachments=mail_attachments,
    )
