"""Zendesk source: support tickets (+ comments) and Help Center articles.

``tickets`` uses the cursor-based incremental export, which is the only
endpoint that returns every ticket regardless of age; ``start_time`` is the
stored cursor (or ``start_date`` on the first run).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    NextUrlPagination,
    Paginator,
    StreamSpec,
    as_epoch_seconds,
)
from ..common.rest_source import basic_auth_header
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


@dataclass(frozen=True)
class _IncrementalExportPagination(Paginator):
    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if not payload or payload.get("end_of_stream") or not payload.get("after_cursor"):
            return None
        req.params = {"cursor": payload["after_cursor"]}
        return req


class ZendeskConfig(BaseModel):
    subdomain: str = Field(description="'acme' for acme.zendesk.com.")
    email: str | None = Field(default=None, description="Agent e-mail (API token auth).")
    api_token: str | None = secret_field(
        default=None,
        description="API token (with email). No credentials at all: anonymous, which reads "
        "the public Help Center articles only.",
    )
    oauth_token: str | None = secret_field(default=None, description="Alternative to e-mail/token.")
    start_date: str = Field(default="2015-01-01T00:00:00Z", description="First-run lower bound.")
    include_comments: bool = True
    timeout_seconds: float = 60.0


class ZendeskSource(DeclarativeRestSource[ZendeskConfig]):
    definition = ConnectorDefinition(
        name="zendesk",
        display_name="Zendesk",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developer.zendesk.com/api-reference/",
        icon="zendesk.svg",
        tags=frozenset({"saas", "support", "helpdesk"}),
    )
    Config = ZendeskConfig

    def base_url(self) -> str:
        return f"https://{self.config.subdomain}.zendesk.com"

    def auth_headers(self) -> dict[str, str]:
        if self.config.oauth_token:
            return {"Authorization": f"Bearer {self.config.oauth_token}"}
        if self.config.api_token:
            return basic_auth_header(f"{self.config.email}/token", self.config.api_token)
        return {}  # anonymous: the Help Center is public, tickets are not

    def streams(self) -> list[StreamSpec]:
        specs = [
            StreamSpec(
                name="tickets",
                path="/api/v2/incremental/tickets/cursor.json",
                records_path="tickets",
                params={"start_time": as_epoch_seconds(self.config.start_date)},
                paginator=_IncrementalExportPagination(),
                cursor_field="updated_at",
                incremental_param="start_time",
                cursor_format=as_epoch_seconds,
            ),
            StreamSpec(
                name="articles",
                path="/api/v2/help_center/articles.json",
                records_path="articles",
                params={"sort_by": "updated_at", "sort_order": "asc", "per_page": 100},
                paginator=NextUrlPagination(next_url_path="next_page"),
                cursor_field="updated_at",
                client_side_filter=True,
                transform=_article_text,
            ),
        ]
        if self.config.include_comments:
            specs.append(
                StreamSpec(
                    name="ticket_comments",
                    path="/api/v2/tickets/{parent[id]}/comments.json",
                    records_path="comments",
                    paginator=NextUrlPagination(next_url_path="next_page"),
                    parent="tickets",
                    parent_field="ticket_id",
                    # A comment moves its ticket's updated_at: an incremental run exports
                    # only the tickets changed since the comments cursor, not every ticket.
                    parent_uses_cursor=True,
                    cursor_field="created_at",
                    client_side_filter=True,
                )
            )
        return specs


def _article_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["body_text"] = html_to_text(rec.get("body"))
    return rec
