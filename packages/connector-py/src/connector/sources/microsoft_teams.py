"""Microsoft Teams source via Microsoft Graph.

Streams: ``teams``, ``channels`` and ``messages``. Channel messages use the Graph
*delta* API; the ``deltaLink`` of every channel is the stored state, so later
syncs only receive new and edited messages. Requires application permissions
``Team.ReadBasic.All``, ``Channel.ReadBasic.All`` and ``ChannelMessage.Read.All``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import Field

from ..common.microsoft_graph import DeltaQuery, GraphConfigBase, GraphSource
from ..common.text import html_to_text
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

TEAM_FILTER = "resourceProvisioningOptions/Any(x:x eq 'Team')"


class MicrosoftTeamsConfig(GraphConfigBase):
    team_names: list[str] | None = Field(default=None, description="Restrict to these teams.")
    include_replies: bool = Field(default=False, description="Also fetch replies of each message.")


class MicrosoftTeamsSource(GraphSource[MicrosoftTeamsConfig]):
    definition = ConnectorDefinition(
        name="microsoft_teams",
        display_name="Microsoft Teams",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://learn.microsoft.com/graph/api/resources/teams-api-overview",
        icon="microsoft_teams.svg",
        tags=frozenset({"saas", "microsoft", "chat"}),
    )
    Config = MicrosoftTeamsConfig

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(name="teams", source_defined_primary_key=[["id"]]),
                Stream(name="channels", source_defined_primary_key=[["id"]]),
                Stream(
                    name="messages",
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["last_modified"],
                    source_defined_primary_key=[["id"]],
                ),
            ]
        )

    async def _teams(self) -> list[dict[str, Any]]:
        params = {"$filter": TEAM_FILTER, "$select": "id,displayName,description,mail"}
        teams = [t async for t in self.paginate("/groups", params=params)]
        if self.config.team_names:
            wanted = set(self.config.team_names)
            teams = [t for t in teams if t.get("displayName") in wanted]
        return teams

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        wanted = set(catalog.names())
        if not wanted & {"teams", "channels", "messages"}:
            return
        teams = await self._teams()
        channels: list[dict[str, Any]] = []
        for team in teams:
            if "teams" in wanted:
                yield Record(stream="teams", data=team)
            if wanted & {"channels", "messages"}:
                async for ch in self.paginate(f"/teams/{team['id']}/channels"):
                    ch["team_id"] = team["id"]
                    ch["team_name"] = team.get("displayName")
                    channels.append(ch)
                    if "channels" in wanted:
                        yield Record(stream="channels", data=ch)
        if "messages" not in wanted:
            return
        configured = next(s for s in catalog.streams if s.stream.name == "messages")
        incremental = configured.sync_mode is SyncMode.INCREMENTAL
        links: dict[str, str] = (
            dict(state.get("messages").get("delta_links") or {}) if incremental else {}
        )
        new_links: dict[str, str] = {}
        for ch in channels:
            base = f"/teams/{ch['team_id']}/channels/{ch['id']}/messages"
            changes = self.delta(f"{base}/delta", resume_from=links.get(ch["id"]))
            async for raw in _readable(changes):
                yield Record(stream="messages", data=_message(raw, ch))
                if self.config.include_replies:
                    # Not part of "may this channel be read": a failure here is the sync's.
                    async for reply in self.paginate(f"{base}/{raw['id']}/replies"):
                        yield Record(stream="messages", data=_message(reply, ch, raw["id"]))
            if changes.delta_link:
                new_links[ch["id"]] = changes.delta_link
        if incremental and new_links:
            yield State(stream="messages", data={"delta_links": {**links, **new_links}})


async def _readable(changes: DeltaQuery) -> AsyncIterator[dict[str, Any]]:
    """The messages of one channel; none for a channel the app may not read or that is gone.

    Only the delta query itself is excused. What the caller does with a message
    (fetching its replies) happens outside this generator, so an error there is
    not mistaken for an unreadable channel.
    """
    try:
        async for raw in changes:
            yield raw
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (403, 404):
            raise


def _message(
    raw: dict[str, Any], channel: dict[str, Any], reply_to: str | None = None
) -> dict[str, Any]:
    body = raw.get("body") or {}
    content = body.get("content") or ""
    sender = ((raw.get("from") or {}).get("user") or {}).get("displayName")
    return {
        "id": raw.get("id"),
        "team_id": channel.get("team_id"),
        "team_name": channel.get("team_name"),
        "channel_id": channel.get("id"),
        "channel_name": channel.get("displayName"),
        "reply_to_id": reply_to or raw.get("replyToId"),
        "subject": raw.get("subject"),
        "text": html_to_text(content) if body.get("contentType") == "html" else content,
        "from": sender,
        "message_type": raw.get("messageType"),
        "deleted": raw.get("deletedDateTime") is not None,
        "web_url": raw.get("webUrl"),
        "created": raw.get("createdDateTime"),
        "last_modified": raw.get("lastModifiedDateTime") or raw.get("createdDateTime"),
    }
