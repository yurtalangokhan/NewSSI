"""Zulip source: streams (channels) and messages.

Messages are read forward from an anchor: ``oldest`` on the first run, then the
highest message id seen. Paging stops when the server reports ``found_newest``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, Paginator, StreamSpec, from_epoch_seconds
from ..common.rest_source import basic_auth_header
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


@dataclass(frozen=True)
class _AnchorPagination(Paginator):
    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if not records or not payload or payload.get("found_newest"):
            return None
        req.params["anchor"] = records[-1]["id"]
        req.params["include_anchor"] = "false"
        return req


class ZulipConfig(BaseModel):
    site_url: str = Field(description="e.g. https://acme.zulipchat.com")
    email: str = Field(description="Bot or user e-mail.")
    api_key: str = secret_field()
    stream_names: list[str] | None = Field(default=None, description="Restrict messages to these.")
    timeout_seconds: float = 60.0
    verify_ssl: bool = True


class ZulipSource(DeclarativeRestSource[ZulipConfig]):
    definition = ConnectorDefinition(
        name="zulip",
        display_name="Zulip",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://zulip.com/api/rest",
        icon="zulip.svg",
        tags=frozenset({"chat", "self-hosted"}),
    )
    Config = ZulipConfig

    def base_url(self) -> str:
        return self.config.site_url.rstrip("/") + "/api/v1"

    def auth_headers(self) -> dict[str, str]:
        return basic_auth_header(self.config.email, self.config.api_key)

    def streams(self) -> list[StreamSpec]:
        names = list(self.config.stream_names or [])
        # A narrow ANDs its terms, so it can express one stream only; filter the rest here.
        narrow = [{"operator": "stream", "operand": names[0]}] if len(names) == 1 else []
        wanted = set(names) if len(names) > 1 else set()

        def message(rec: dict[str, Any]) -> dict[str, Any] | None:
            rec = _message(rec)
            return rec if not wanted or rec.get("stream_name") in wanted else None

        return [
            StreamSpec(
                name="streams",
                path="/streams",
                records_path="streams",
                primary_key=("stream_id",),
            ),
            StreamSpec(
                name="messages",
                path="/messages",
                records_path="messages",
                params={
                    "anchor": "oldest",
                    "num_before": 0,
                    "num_after": 1000,
                    "narrow": json.dumps(narrow),
                    "apply_markdown": "false",
                },
                paginator=_AnchorPagination(),
                cursor_field="id",
                incremental_param="anchor",
                cursor_format=int,
                on_request=_exclude_anchor,
                transform=message,
            ),
        ]


def _exclude_anchor(req: Any, cursor: Any) -> None:
    if cursor is not None:
        req.params["include_anchor"] = "false"


def _message(rec: dict[str, Any]) -> dict[str, Any]:
    rec["sent_at"] = from_epoch_seconds(rec.get("timestamp"))
    rec["stream_name"] = rec.get("display_recipient") if rec.get("type") == "stream" else None
    return rec
