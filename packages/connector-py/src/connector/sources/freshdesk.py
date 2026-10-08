"""Freshdesk source: tickets, contacts, companies and the solutions knowledge base.

Freshdesk only lists tickets of the last 30 days unless ``updated_since`` is
sent, so the first run uses ``start_date``. A ticket query serves at most 300
pages; a larger backlog is read as a chain of queries (see
:class:`_TicketPagination`).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    PageNumberPagination,
    StreamSpec,
    as_iso_z,
)
from ..common.rest_source import basic_auth_header
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

logger = logging.getLogger("connector.freshdesk")

_PAGER = PageNumberPagination(page_param="page", size_param="per_page", page_size=100)


@dataclass(frozen=True)
class _TicketPagination(PageNumberPagination):
    """Page numbers up to ``max_page``, then a new query from the last stamp seen.

    The listing is ordered by ``updated_at`` ascending, so ``updated_since`` = the last
    record's stamp continues where the capped query stopped. The boundary ticket is read
    twice (nothing sharing its stamp may be lost); record keys absorb the duplicate.
    """

    page_param: str = "page"
    size_param: str | None = "per_page"
    page_size: int = 100
    max_page: int = 300
    anchor_param: str = "updated_since"
    anchor_field: str = "updated_at"

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        nxt = super().next(req, response, payload, records)
        if nxt is None or int(req.params.get(self.page_param, self.first_page)) <= self.max_page:
            return nxt
        last = records[-1] if isinstance(records[-1], Mapping) else {}
        stamp = last.get(self.anchor_field)
        anchor = as_iso_z(stamp) if stamp else None
        if not anchor or anchor == req.params.get(self.anchor_param):
            logger.warning("tickets: cannot move past %s pages at one stamp", self.max_page)
            return None
        req.params[self.anchor_param] = anchor
        req.params[self.page_param] = self.first_page
        return req


_TICKET_PAGER = _TicketPagination()


class FreshdeskConfig(BaseModel):
    domain: str = Field(description="'acme' for acme.freshdesk.com.")
    api_key: str = secret_field()
    start_date: str = Field(default="2015-01-01T00:00:00Z", description="First-run lower bound.")
    include_solutions: bool = True
    timeout_seconds: float = 60.0


class FreshdeskSource(DeclarativeRestSource[FreshdeskConfig]):
    definition = ConnectorDefinition(
        name="freshdesk",
        display_name="Freshdesk",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developers.freshdesk.com/api/",
        icon="freshdesk.svg",
        tags=frozenset({"saas", "support", "helpdesk"}),
    )
    Config = FreshdeskConfig

    def base_url(self) -> str:
        domain = self.config.domain
        return domain if domain.startswith("http") else f"https://{domain}.freshdesk.com"

    def auth_headers(self) -> dict[str, str]:
        return basic_auth_header(self.config.api_key, "X")

    def streams(self) -> list[StreamSpec]:
        specs = [
            StreamSpec(
                name="tickets",
                path="/api/v2/tickets",
                params={
                    "updated_since": as_iso_z(self.config.start_date),
                    "order_by": "updated_at",
                    "order_type": "asc",
                    "include": "description",
                },
                paginator=_TICKET_PAGER,
                cursor_field="updated_at",
                incremental_param="updated_since",
                cursor_format=as_iso_z,
            ),
            StreamSpec(
                name="contacts",
                path="/api/v2/contacts",
                paginator=_PAGER,
                cursor_field="updated_at",
                incremental_param="_updated_since",
                cursor_format=as_iso_z,
            ),
            StreamSpec(
                name="companies",
                path="/api/v2/companies",
                paginator=_PAGER,
                cursor_field="updated_at",
                client_side_filter=True,
            ),
        ]
        if self.config.include_solutions:
            specs += [
                StreamSpec(name="solution_categories", path="/api/v2/solutions/categories"),
                StreamSpec(
                    name="solution_folders",
                    path="/api/v2/solutions/categories/{parent[id]}/folders",
                    parent="solution_categories",
                    parent_field="category_id",
                ),
                StreamSpec(
                    name="solution_articles",
                    path="/api/v2/solutions/folders/{parent[id]}/articles",
                    paginator=_PAGER,
                    parent="solution_folders",
                    parent_field="folder_id",
                    cursor_field="updated_at",
                    client_side_filter=True,
                    transform=_article_text,
                ),
            ]
        return specs


def _article_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["description_text"] = rec.get("description_text") or html_to_text(rec.get("description"))
    return rec
