"""TestRail source: projects, suites and test cases.

TestRail routes through ``index.php?/api/v2/<method>&k=v``: the API method is
itself the first query component, so the URL is assembled by hand instead of
through httpx ``params``. Works with both the paged envelope (6.7+) and the
bare lists older servers return.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    OffsetPagination,
    PageRequest,
    StreamSpec,
    as_epoch_seconds,
)
from ..common.rest_source import basic_auth_header
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = OffsetPagination(page_size=250)


class TestRailConfig(BaseModel):
    base_url: str = Field(description="e.g. https://acme.testrail.io")
    username: str = Field(description="User e-mail.")
    api_key: str = secret_field(description="API key (or password).")
    project_ids: list[int] | None = Field(default=None, description="Restrict to these projects.")
    timeout_seconds: float = 60.0
    verify_ssl: bool = True


class TestRailSource(DeclarativeRestSource[TestRailConfig]):
    __test__ = False  # not a pytest class, despite the name

    definition = ConnectorDefinition(
        name="testrail",
        display_name="TestRail",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://support.testrail.com/hc/en-us/categories/7076541806228-API-Manual",
        icon="testrail.svg",
        tags=frozenset({"saas", "qa", "testing-tools"}),
    )
    Config = TestRailConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {
            **basic_auth_header(self.config.username, self.config.api_key),
            "Content-Type": "application/json",
        }

    def streams(self) -> list[StreamSpec]:
        wanted = set(self.config.project_ids or [])
        return [
            StreamSpec(
                name="projects",
                path="get_projects",
                records_path="projects",
                paginator=_PAGER,
                transform=(lambda r: r if not wanted or r.get("id") in wanted else None),
            ),
            StreamSpec(
                name="suites",
                path="get_suites/{parent[id]}",
                records_path="suites",
                parent="projects",
            ),
            StreamSpec(
                name="cases",
                path="get_cases/{parent[project_id]}&suite_id={parent[id]}",
                records_path="cases",
                paginator=_PAGER,
                parent="suites",
                cursor_field="updated_on",
                incremental_param="updated_after",
                cursor_format=as_epoch_seconds,
            ),
        ]

    async def _fetch_page(
        self, spec: StreamSpec, req: PageRequest
    ) -> tuple[httpx.Response, Any, list[Any]]:
        query = urlencode(req.params)
        url = f"/index.php?/api/v2/{req.url}" + (f"&{query}" if query else "")
        folded = PageRequest(method=req.method, url=url, params={}, headers=req.headers)
        return await super()._fetch_page(spec, folded)
