"""Generic HTTP JSON API source.

Fetches a JSON endpoint (optionally paginated) and exposes it as a single
stream. Good enough for internal REST APIs and many SaaS list endpoints;
subclass and override ``_next_page`` for exotic pagination.

Requests go through :class:`~connector.common.rest_source.RestSource`, so a
``429`` or ``5xx`` answer is retried (honouring ``Retry-After``) like for every
other API source.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from ..base import secret_field, sensitive_mapping_field
from ..common.declarative import dig, page_signature
from ..common.json_schema import add_properties
from ..common.rest_source import RestSource, split_query
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncState,
)

logger = logging.getLogger("connector.http_json")


class HttpJsonConfig(BaseModel):
    url: str = Field(description="Endpoint returning JSON.")
    stream_name: str = Field(default="records", description="Name of the emitted stream.")
    records_path: str | None = Field(
        default=None,
        description="Dot path to the list of records inside the response, e.g. 'data.items'. "
        "Leave empty when the response itself is a list.",
    )
    method: Literal["GET", "POST"] = "GET"
    # An API key travels in any of the three, next to values that are no secret.
    headers: dict[str, str] = sensitive_mapping_field(default_factory=dict)
    params: dict[str, Any] = sensitive_mapping_field(default_factory=dict)
    body: dict[str, Any] | None = sensitive_mapping_field(default=None)
    bearer_token: str | None = secret_field(
        default=None, description="Sent as Authorization: Bearer."
    )
    pagination: Literal["none", "page", "cursor"] = "none"
    page_param: str = "page"
    page_size_param: str | None = None
    page_size: int = 100
    cursor_param: str = "cursor"
    next_cursor_path: str = Field(
        default="next", description="Dot path to the next cursor in the response."
    )
    max_pages: int = Field(default=1000, ge=1)
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class HttpJsonSource(RestSource[HttpJsonConfig]):
    definition = ConnectorDefinition(
        name="http_json",
        icon="http_json.svg",
        display_name="HTTP JSON API",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.API,
        tags=frozenset({"api", "http"}),
    )
    Config = HttpJsonConfig
    # The address and the headers are free text. Followed, a redirect would hand
    # those headers (an API key, say) to whatever host the answer names.
    follow_redirects = False

    # ---- http -------------------------------------------------------------

    def base_url(self) -> str:
        return ""  # ``url`` is absolute

    def auth_headers(self) -> dict[str, str]:
        headers = dict(self.config.headers)
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        return headers

    async def _fetch(self, params: dict[str, Any]) -> Any:
        # The address may carry a query of its own; it stays when parameters are added.
        url, query = split_query(self.config.url, params)
        resp = await self.request(
            self.config.method,
            url,
            params=query or None,
            json=self.config.body if self.config.method == "POST" else None,
        )
        return resp.json()

    def _extract(self, payload: Any) -> list[dict[str, Any]]:
        node = dig(payload, self.config.records_path)
        if node is None:
            return []
        if isinstance(node, dict):
            return [node]
        return [r for r in node if isinstance(r, dict)]

    def _next_page(self, payload: Any, page: int, params: dict[str, Any]) -> dict[str, Any] | None:
        """Return params for the next request or ``None`` when done."""
        cfg = self.config
        if cfg.pagination == "page":
            nxt = dict(params)
            nxt[cfg.page_param] = page + 1
            if cfg.page_size_param:
                nxt[cfg.page_size_param] = cfg.page_size
            return nxt
        if cfg.pagination == "cursor":
            cursor = dig(payload, cfg.next_cursor_path)
            if not cursor:
                return None
            nxt = dict(params)
            nxt[cfg.cursor_param] = cursor
            return nxt
        return None

    # ---- connector API ------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            payload = await self._fetch(self._initial_params())
        except (httpx.HTTPError, ValueError) as exc:
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        try:
            self._extract(payload)
        except (TypeError, AttributeError) as exc:
            return CheckResult(ok=False, message=f"records_path did not resolve to a list: {exc}")
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        payload = await self._fetch(self._initial_params())
        props: dict[str, Any] = {}
        for row in self._extract(payload)[:50]:
            add_properties(props, row)
        return Catalog(
            streams=[
                Stream(
                    name=self.config.stream_name,
                    json_schema={"type": "object", "properties": props},
                )
            ]
        )

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        if self.config.stream_name not in catalog.names():
            return
        params = self._initial_params()
        previous: str | None = None
        for page in range(1, self.config.max_pages + 1):
            payload = await self._fetch(params)
            rows = self._extract(payload)
            if not rows:
                return
            signature = page_signature(rows)
            if signature == previous:
                # The API ignored the paging parameters and served the same page again.
                logger.warning("%s: page repeated, stopping pagination", self.config.stream_name)
                return
            previous = signature
            for row in rows:
                yield Record(stream=self.config.stream_name, data=row)
            nxt = self._next_page(payload, page, params)
            if nxt is None:
                return
            params = nxt

    def _initial_params(self) -> dict[str, Any]:
        params = dict(self.config.params)
        if self.config.pagination == "page":
            params.setdefault(self.config.page_param, 1)
            if self.config.page_size_param:
                params.setdefault(self.config.page_size_param, self.config.page_size)
        return params
