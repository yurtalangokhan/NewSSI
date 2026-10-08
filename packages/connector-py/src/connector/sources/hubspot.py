"""HubSpot source: CRM objects (contacts, companies, deals, tickets by default).

A full refresh pages through the object *list* endpoint. An incremental run
switches to the *search* endpoint, which can filter and sort by the
last-modified property. HubSpot caps a search at 10 000 results; a larger gap
is read as a chain of searches, each starting at the last stamp of the one before.
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
    PageRequest,
    Paginator,
    StreamSpec,
    as_epoch_millis,
    dig,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

DEFAULT_PROPERTIES: dict[str, list[str]] = {
    "contacts": [
        "email",
        "firstname",
        "lastname",
        "phone",
        "company",
        "jobtitle",
        "lifecyclestage",
    ],
    "companies": ["name", "domain", "industry", "description", "city", "country"],
    "deals": ["dealname", "amount", "dealstage", "pipeline", "closedate", "description"],
    "tickets": ["subject", "content", "hs_pipeline_stage", "hs_ticket_priority"],
}
_PAGE = 100
SEARCH_RESULT_CAP = 10_000
"""HubSpot answers 400 to a search paged past this many results."""

logger = logging.getLogger("connector.hubspot")


def _modified_property(obj: str) -> str:
    return "lastmodifieddate" if obj == "contacts" else "hs_lastmodifieddate"


@dataclass(frozen=True)
class _AfterPagination(Paginator):
    """``paging.next.after`` goes into the query for GET and into the body for search.

    A search sorted by ``modified`` that reaches :data:`SEARCH_RESULT_CAP` is started
    again from the last stamp seen (``GTE``, so records sharing that stamp are not lost;
    the boundary record itself is read twice and absorbed by record keys).
    """

    modified: str = "hs_lastmodifieddate"

    def start(self, req: PageRequest) -> None:
        req.params["limit"] = _PAGE

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        after = dig(payload, "paging.next.after")
        if not after:
            return None
        if req.method != "POST":
            req.params["after"] = after
            return req
        if str(after).isdigit() and int(after) >= SEARCH_RESULT_CAP:
            return self._re_anchor(req, records)
        req.body = {**(req.body or {}), "after": after}
        return req

    def _re_anchor(self, req: PageRequest, records: list[Any]) -> PageRequest | None:
        last = records[-1] if records and isinstance(records[-1], Mapping) else None
        stamp = dig(last, f"properties.{self.modified}") or dig(last, "updatedAt")
        value = str(as_epoch_millis(stamp)) if stamp is not None else None
        body = dict(req.body or {})
        current = dig(body, "filterGroups.0.filters.0")
        if value is None or (isinstance(current, Mapping) and current.get("value") == value):
            logger.warning("search cannot move past %s results at one stamp", SEARCH_RESULT_CAP)
            return None
        body.pop("after", None)
        body["filterGroups"] = [
            {"filters": [{"propertyName": self.modified, "operator": "GTE", "value": value}]}
        ]
        req.body = body
        return req


class HubSpotConfig(BaseModel):
    access_token: str = secret_field(description="Private app access token.")
    objects: list[str] = Field(default_factory=lambda: list(DEFAULT_PROPERTIES))
    properties: dict[str, list[str]] = Field(
        default_factory=dict, description="Override the property list per object."
    )
    timeout_seconds: float = 60.0


class HubSpotSource(DeclarativeRestSource[HubSpotConfig]):
    definition = ConnectorDefinition(
        name="hubspot",
        display_name="HubSpot",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SALES,
        documentation_url="https://developers.hubspot.com/docs/api/crm/understanding-the-crm",
        icon="hubspot.svg",
        tags=frozenset({"saas", "crm", "marketing"}),
    )
    Config = HubSpotConfig

    def base_url(self) -> str:
        return "https://api.hubapi.com"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.access_token}"}

    def streams(self) -> list[StreamSpec]:
        return [self._spec(obj) for obj in self.config.objects]

    def _spec(self, obj: str) -> StreamSpec:
        props = self.config.properties.get(obj) or DEFAULT_PROPERTIES.get(obj, [])
        modified = _modified_property(obj)

        def switch_to_search(req: PageRequest, cursor: Any) -> None:
            if cursor is None:
                return
            req.method = "POST"
            req.url = f"/crm/v3/objects/{obj}/search"
            req.params = {}
            req.body = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": modified,
                                "operator": "GT",
                                "value": str(as_epoch_millis(cursor)),
                            }
                        ]
                    }
                ],
                "sorts": [{"propertyName": modified, "direction": "ASCENDING"}],
                "properties": props,
                "limit": _PAGE,
            }

        return StreamSpec(
            name=obj,
            path=f"/crm/v3/objects/{obj}",
            records_path="results",
            params={"properties": ",".join(props) or None, "archived": "false"},
            paginator=_AfterPagination(modified=modified),
            cursor_field="updatedAt",
            on_request=switch_to_search,
            transform=_flatten,
        )


def _flatten(rec: dict[str, Any]) -> dict[str, Any]:
    return {**(rec.get("properties") or {}), **{k: v for k, v in rec.items() if k != "properties"}}
