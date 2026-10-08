"""Discord source: text channels of a guild and their messages.

Messages are paged *forward* with ``after=<snowflake>``: the first request uses
``after=0`` (oldest messages first), later syncs continue from the highest id
seen per channel. Discord returns each page newest-first, so the next ``after``
is the maximum id of the page, not its last element.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, Paginator, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

TEXT_CHANNEL_TYPES = {0, 5, 10, 11, 12}  # text, announcement and thread channels
_PAGE = 100


@dataclass(frozen=True)
class _AfterSnowflakePagination(Paginator):
    def start(self, req) -> None:  # noqa: ANN001
        req.params["limit"] = _PAGE
        req.params.setdefault("after", "0")

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if len(records) < _PAGE:
            return None
        req.params["after"] = str(max(int(r["id"]) for r in records))
        return req


class DiscordConfig(BaseModel):
    bot_token: str = secret_field(description="Bot token.")
    guild_id: str = Field(description="Server (guild) id.")
    channel_ids: list[str] | None = Field(default=None, description="Restrict to these channels.")
    timeout_seconds: float = 60.0


class DiscordSource(DeclarativeRestSource[DiscordConfig]):
    definition = ConnectorDefinition(
        name="discord",
        display_name="Discord",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://discord.com/developers/docs/reference",
        icon="discord.svg",
        tags=frozenset({"chat", "community"}),
    )
    Config = DiscordConfig

    def base_url(self) -> str:
        return "https://discord.com/api/v10"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self.config.bot_token}"}

    def streams(self) -> list[StreamSpec]:
        wanted = set(self.config.channel_ids or [])

        def text_channels(ch: dict[str, Any]) -> dict[str, Any] | None:
            if ch.get("type") not in TEXT_CHANNEL_TYPES:
                return None
            return ch if not wanted or ch.get("id") in wanted else None

        return [
            StreamSpec(
                name="channels",
                path=f"/guilds/{self.config.guild_id}/channels",
                transform=text_channels,
            ),
            StreamSpec(
                name="messages",
                path="/channels/{parent[id]}/messages",
                paginator=_AfterSnowflakePagination(),
                parent="channels",
                parent_field="channel_id",
                per_parent_cursor=True,
                cursor_field="id",
                incremental_param="after",
                cursor_format=str,
                transform=_message,
            ),
        ]


def _message(rec: dict[str, Any]) -> dict[str, Any]:
    author = rec.get("author") or {}
    rec["author_name"] = author.get("global_name") or author.get("username")
    rec["text"] = rec.get("content") or ""
    return rec
