"""Gmail source (service account with domain-wide delegation, or an access token).

Stream ``messages``: the list endpoint only returns ids, so every message is
fetched in ``full`` format and reduced to headers plus a plain-text body.
Incremental sync appends ``after:<epoch>`` to the Gmail search query.
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar

from pydantic import Field

from ..common.declarative import (
    CursorPagination,
    PageRequest,
    StreamSpec,
    as_epoch_seconds,
    from_epoch_millis,
)
from ..common.google_auth import GoogleAuthConfig, GoogleSource
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class GmailConfig(GoogleAuthConfig):
    user_id: str = Field(default="me", description="Mailbox; 'me' is the impersonated subject.")
    query: str | None = Field(default=None, description="Gmail search, e.g. 'label:support'.")
    label_ids: list[str] | None = None
    include_spam_trash: bool = False


class GmailSource(GoogleSource[GmailConfig]):
    definition = ConnectorDefinition(
        name="gmail",
        display_name="Gmail",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://developers.google.com/gmail/api/reference/rest",
        icon="gmail.svg",
        tags=frozenset({"google", "email"}),
    )
    Config = GmailConfig
    scopes: ClassVar[tuple[str, ...]] = ("https://www.googleapis.com/auth/gmail.readonly",)

    def base_url(self) -> str:
        return "https://gmail.googleapis.com"

    def streams(self) -> list[StreamSpec]:
        user = self.config.user_id
        base_query = self.config.query or ""

        def with_cursor(req: PageRequest, cursor: Any) -> None:
            if cursor is not None:
                req.params["q"] = f"{base_query} after:{as_epoch_seconds(cursor)}".strip()

        return [
            StreamSpec(
                name="messages",
                path=f"/gmail/v1/users/{user}/messages",
                records_path="messages",
                params={
                    "q": base_query or None,
                    "labelIds": self.config.label_ids,
                    "includeSpamTrash": "true" if self.config.include_spam_trash else None,
                },
                paginator=CursorPagination(
                    cursor_path="nextPageToken",
                    cursor_param="pageToken",
                    size_param="maxResults",
                    page_size=500,
                ),
                detail_path=f"/gmail/v1/users/{user}/messages/{{record[id]}}",
                detail_params={"format": "full"},
                cursor_field="internal_date",
                on_request=with_cursor,
                transform=_message,
            )
        ]


def _message(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload") or {}
    headers = {h.get("name", "").lower(): h.get("value") for h in payload.get("headers") or []}
    plain, html, attachments = _walk(payload)
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "label_ids": raw.get("labelIds") or [],
        "subject": headers.get("subject"),
        "from": headers.get("from"),
        "to": headers.get("to"),
        "cc": headers.get("cc"),
        "date": headers.get("date"),
        "message_id": headers.get("message-id"),
        "snippet": raw.get("snippet"),
        "body": plain or html_to_text(html),
        "attachments": attachments,
        "internal_date": from_epoch_millis(raw.get("internalDate")),
    }


def _walk(part: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    plain, html, attachments = "", "", []
    mime = part.get("mimeType", "")
    body = part.get("body") or {}
    if part.get("filename"):
        attachments.append(
            {"filename": part["filename"], "mime_type": mime, "size": body.get("size")}
        )
    elif body.get("data"):
        text = base64.urlsafe_b64decode(body["data"] + "=" * (-len(body["data"]) % 4)).decode(
            "utf-8", errors="replace"
        )
        if mime == "text/plain":
            plain = text
        elif mime == "text/html":
            html = text
    for child in part.get("parts") or []:
        p, h, a = _walk(child)
        plain, html = plain + p, html + h
        attachments.extend(a)
    return plain, html, attachments
