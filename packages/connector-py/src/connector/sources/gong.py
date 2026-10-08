"""Gong source: users, calls and call transcripts.

``calls`` is incremental on the call start time. Transcript records carry no
timestamp of their own, so ``transcripts`` is a full refresh bounded by
``start_date``; each transcript is flattened into ``text``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import CursorPagination, DeclarativeRestSource, StreamSpec, as_iso_z
from ..common.rest_source import basic_auth_header
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_QUERY_CURSOR = CursorPagination(cursor_path="records.cursor", cursor_param="cursor")
_BODY_CURSOR = CursorPagination(cursor_path="records.cursor", cursor_param="cursor", in_body=True)


class GongConfig(BaseModel):
    access_key: str = secret_field()
    access_key_secret: str = secret_field()
    base_url: str = Field(default="https://api.gong.io", description="Your company's API base URL.")
    start_date: str = Field(default="2015-01-01T00:00:00Z", description="Earliest call to read.")
    timeout_seconds: float = 120.0


class GongSource(DeclarativeRestSource[GongConfig]):
    definition = ConnectorDefinition(
        name="gong",
        display_name="Gong",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SALES,
        documentation_url="https://gong.app.gong.io/settings/api/documentation",
        icon="gong.svg",
        tags=frozenset({"saas", "calls", "transcripts"}),
    )
    Config = GongConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return basic_auth_header(self.config.access_key, self.config.access_key_secret)

    def streams(self) -> list[StreamSpec]:
        since = as_iso_z(self.config.start_date)
        return [
            StreamSpec(
                name="users", path="/v2/users", records_path="users", paginator=_QUERY_CURSOR
            ),
            StreamSpec(
                name="calls",
                path="/v2/calls",
                records_path="calls",
                params={"fromDateTime": since},
                paginator=_QUERY_CURSOR,
                cursor_field="started",
                incremental_param="fromDateTime",
                cursor_format=as_iso_z,
            ),
            StreamSpec(
                name="transcripts",
                path="/v2/calls/transcript",
                method="POST",
                body={"filter": {"fromDateTime": since}},
                records_path="callTranscripts",
                paginator=_BODY_CURSOR,
                primary_key=("callId",),
                transform=_transcript_text,
            ),
        ]


def _transcript_text(rec: dict[str, Any]) -> dict[str, Any]:
    lines = []
    for turn in rec.get("transcript") or []:
        text = " ".join(s.get("text", "") for s in turn.get("sentences") or [])
        if text:
            lines.append(f"{turn.get('speakerId', '')}: {text}".lstrip(": "))
    rec["text"] = "\n".join(lines)
    return rec
