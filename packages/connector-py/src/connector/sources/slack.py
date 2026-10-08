"""Slack source: channels, users and channel messages.

Slack answers ``200 OK`` with ``{"ok": false, "error": ...}`` on failure; that is
surfaced as an API error. The bot only sees history of channels it is a member
of, so ``not_in_channel`` skips that channel instead of failing the sync.
Thread replies are not expanded (``reply_count`` tells whether a thread exists).
The incremental cursor (message ``ts``) is tracked per channel.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    CursorPagination,
    DeclarativeRestSource,
    StreamSpec,
    from_epoch_seconds,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = CursorPagination(
    cursor_path="response_metadata.next_cursor",
    cursor_param="cursor",
    size_param="limit",
    page_size=200,
)


def _slack_error(payload: Any) -> str | None:
    if isinstance(payload, dict) and payload.get("ok") is False:
        return str(payload.get("error") or "unknown_error")
    return None


class SlackConfig(BaseModel):
    bot_token: str = secret_field(description="Bot token (xoxb-...).")
    channel_types: str = Field(default="public_channel,private_channel")
    channel_names: list[str] | None = Field(default=None, description="Restrict to these channels.")
    include_archived: bool = False
    timeout_seconds: float = 60.0


class SlackSource(DeclarativeRestSource[SlackConfig]):
    definition = ConnectorDefinition(
        name="slack",
        display_name="Slack",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://api.slack.com/methods",
        icon="slack.svg",
        tags=frozenset({"saas", "chat"}),
    )
    Config = SlackConfig

    def base_url(self) -> str:
        return "https://slack.com/api"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.bot_token}"}

    def streams(self) -> list[StreamSpec]:
        wanted = {n.lstrip("#") for n in self.config.channel_names or []}
        return [
            StreamSpec(
                name="channels",
                path="/conversations.list",
                records_path="channels",
                params={
                    "types": self.config.channel_types,
                    "exclude_archived": "false" if self.config.include_archived else "true",
                },
                paginator=_PAGER,
                error_check=_slack_error,
                transform=(lambda c: c if not wanted or c.get("name") in wanted else None),
            ),
            StreamSpec(
                name="users",
                path="/users.list",
                records_path="members",
                paginator=_PAGER,
                error_check=_slack_error,
            ),
            StreamSpec(
                name="messages",
                path="/conversations.history?channel={parent[id]}",
                records_path="messages",
                paginator=_PAGER,
                primary_key=("channel_id", "ts"),
                parent="channels",
                parent_field="channel_id",
                per_parent_cursor=True,
                cursor_field="ts",
                incremental_param="oldest",
                cursor_format=str,
                error_check=_slack_error,
                transform=_message,
            ),
        ]


def _message(rec: dict[str, Any]) -> dict[str, Any]:
    rec["sent_at"] = from_epoch_seconds(rec.get("ts"))
    return rec
