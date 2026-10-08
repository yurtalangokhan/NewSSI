"""Outlook (Exchange Online) source via Microsoft Graph.

Streams, per configured mailbox (``user_principal_names``):

* ``messages``  – mail with text body; incremental on ``lastModifiedDateTime``
* ``events``    – calendar events; incremental on ``lastModifiedDateTime``

Requires an app registration with application permissions ``Mail.Read`` and
``Calendars.Read`` (admin consent). Attachments are not downloaded; their
names are listed so a downstream step can fetch them if needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import Field

from ..common.cursor import CursorTracker
from ..common.microsoft_graph import GraphConfigBase, GraphSource
from ..models import (
    Catalog,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)

MESSAGE_SELECT = (
    "id,subject,bodyPreview,body,from,toRecipients,ccRecipients,receivedDateTime,"
    "sentDateTime,lastModifiedDateTime,hasAttachments,importance,isRead,conversationId,"
    "webLink,parentFolderId,categories"
)
EVENT_SELECT = (
    "id,subject,bodyPreview,body,start,end,location,organizer,attendees,isAllDay,isCancelled,"
    "lastModifiedDateTime,webLink,categories"
)


class OutlookConfig(GraphConfigBase):
    user_principal_names: list[str] = Field(
        description="Mailboxes to read, e.g. ['sales@acme.com']."
    )
    folders: list[str] | None = Field(
        default=None,
        description="Well-known folder names (inbox, sentitems, ...) or folder ids. Default: all.",
    )
    include_attachments_list: bool = True
    body_as_text: bool = Field(
        default=True, description="Ask Graph for text instead of HTML bodies."
    )


class OutlookSource(GraphSource[OutlookConfig]):
    definition = ConnectorDefinition(
        name="outlook",
        display_name="Outlook (Microsoft 365)",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://learn.microsoft.com/graph/api/resources/mail-api-overview",
        icon="outlook.svg",
        tags=frozenset({"saas", "microsoft", "email"}),
    )
    Config = OutlookConfig

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def discover(self) -> Catalog:
        base = {
            "id": {"type": "string"},
            "mailbox": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "web_link": {"type": "string"},
            "last_modified": {"type": "string", "format": "date-time"},
        }
        return Catalog(
            streams=[
                Stream(
                    name="messages",
                    json_schema={
                        "type": "object",
                        "properties": {
                            **base,
                            "from": {"type": "string"},
                            "to": {"type": "array"},
                            "cc": {"type": "array"},
                            "received": {"type": "string", "format": "date-time"},
                            "has_attachments": {"type": "boolean"},
                            "attachments": {"type": "array"},
                            "folder_id": {"type": "string"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["last_modified"],
                    source_defined_primary_key=[["id"]],
                ),
                Stream(
                    name="events",
                    json_schema={
                        "type": "object",
                        "properties": {
                            **base,
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                            "location": {"type": "string"},
                            "organizer": {"type": "string"},
                            "attendees": {"type": "array"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["last_modified"],
                    source_defined_primary_key=[["id"]],
                ),
            ]
        )

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        headers = {"Prefer": 'outlook.body-content-type="text"'} if self.config.body_as_text else {}
        for configured in catalog.streams:
            name = configured.stream.name
            if name not in ("messages", "events"):
                continue
            tracker = CursorTracker(
                name, state, enabled=configured.sync_mode is SyncMode.INCREMENTAL
            )
            params: dict[str, Any] = {
                "$select": MESSAGE_SELECT if name == "messages" else EVENT_SELECT,
                "$top": self.config.page_size,
                "$orderby": "lastModifiedDateTime asc",
            }
            if tracker.start:
                params["$filter"] = f"lastModifiedDateTime gt {tracker.start}"
            for upn in self.config.user_principal_names:
                for path in self._paths(upn, name):
                    async for raw in self.paginate(path, params=params, headers=headers):
                        item = _message(raw, upn) if name == "messages" else _event(raw, upn)
                        if (
                            name == "messages"
                            and self.config.include_attachments_list
                            and raw.get("hasAttachments")
                        ):
                            item["attachments"] = await self._attachment_names(upn, raw["id"])
                        tracker.observe(item["last_modified"])
                        yield Record(stream=name, data=item)
            if final := tracker.final_state():
                yield final

    def _paths(self, upn: str, stream: str) -> list[str]:
        user = f"/users/{upn}"
        if stream == "events":
            return [f"{user}/events"]
        if self.config.folders:
            return [f"{user}/mailFolders/{f}/messages" for f in self.config.folders]
        return [f"{user}/messages"]

    async def _attachment_names(self, upn: str, message_id: str) -> list[dict[str, Any]]:
        page = await self.get_json(
            f"/users/{upn}/messages/{message_id}/attachments",
            params={"$select": "id,name,contentType,size"},
        )
        return [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "content_type": a.get("contentType"),
                "size": a.get("size"),
            }
            for a in page.get("value", []) or []
        ]


def _addr(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    email = value.get("emailAddress") or {}
    return email.get("address") or email.get("name")


def _message(raw: dict[str, Any], upn: str) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "mailbox": upn,
        "subject": raw.get("subject"),
        "body": (raw.get("body") or {}).get("content") or raw.get("bodyPreview"),
        "from": _addr(raw.get("from")),
        "to": [_addr(r) for r in raw.get("toRecipients") or []],
        "cc": [_addr(r) for r in raw.get("ccRecipients") or []],
        "received": raw.get("receivedDateTime"),
        "sent": raw.get("sentDateTime"),
        "has_attachments": bool(raw.get("hasAttachments")),
        "attachments": [],
        "importance": raw.get("importance"),
        "is_read": raw.get("isRead"),
        "conversation_id": raw.get("conversationId"),
        "folder_id": raw.get("parentFolderId"),
        "categories": raw.get("categories") or [],
        "web_link": raw.get("webLink"),
        "last_modified": raw.get("lastModifiedDateTime"),
    }


def _event(raw: dict[str, Any], upn: str) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "mailbox": upn,
        "subject": raw.get("subject"),
        "body": (raw.get("body") or {}).get("content") or raw.get("bodyPreview"),
        "start": (raw.get("start") or {}).get("dateTime"),
        "end": (raw.get("end") or {}).get("dateTime"),
        "location": (raw.get("location") or {}).get("displayName"),
        "organizer": _addr(raw.get("organizer")),
        "attendees": [_addr(a) for a in raw.get("attendees") or []],
        "is_all_day": raw.get("isAllDay"),
        "is_cancelled": raw.get("isCancelled"),
        "categories": raw.get("categories") or [],
        "web_link": raw.get("webLink"),
        "last_modified": raw.get("lastModifiedDateTime"),
    }
