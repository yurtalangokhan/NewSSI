"""Airtable source: one stream per table of a base.

Tables are discovered through the metadata API unless ``tables`` is given.
Records are flattened (``fields`` merged into the top level). Airtable has no
built-in modification timestamp; name a "Last modified time" field in
``last_modified_field`` to enable incremental sync.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    CursorPagination,
    DeclarativeRestSource,
    PageRequest,
    StreamSpec,
    as_iso,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = CursorPagination(
    cursor_path="offset", cursor_param="offset", size_param="pageSize", page_size=100
)


class AirtableConfig(BaseModel):
    api_token: str = secret_field(description="Personal access token.")
    base_id: str = Field(description="Base id (app...).")
    tables: list[str] | None = Field(default=None, description="Table names or ids. Default: all.")
    view: str | None = None
    last_modified_field: str | None = Field(
        default=None, description="Name of a 'Last modified time' field, for incremental sync."
    )
    timeout_seconds: float = 30.0


class AirtableSource(DeclarativeRestSource[AirtableConfig]):
    definition = ConnectorDefinition(
        name="airtable",
        display_name="Airtable",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://airtable.com/developers/web/api/introduction",
        icon="airtable.svg",
        tags=frozenset({"saas", "database", "spreadsheet"}),
    )
    Config = AirtableConfig
    _tables: list[dict[str, Any]] | None = None

    def base_url(self) -> str:
        return "https://api.airtable.com"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def streams(self) -> list[StreamSpec]:
        return [self._spec(name, name) for name in self.config.tables or []]

    async def stream_specs(self) -> list[StreamSpec]:
        if self.config.tables:
            return self.streams()
        if self._tables is None:
            meta = await self.get_json(f"/v0/meta/bases/{self.config.base_id}/tables")
            self._tables = meta.get("tables", []) or []
        return [self._spec(t["name"], t["id"]) for t in self._tables]

    def _spec(self, name: str, ref: str) -> StreamSpec:
        field = self.config.last_modified_field

        def with_formula(req: PageRequest, cursor: Any) -> None:
            if cursor is not None and field:
                req.params["filterByFormula"] = f"IS_AFTER({{{field}}}, '{as_iso(cursor)}')"

        return StreamSpec(
            name=re.sub(r"\W+", "_", name).strip("_").lower() or ref,
            path=f"/v0/{self.config.base_id}/{ref}",
            records_path="records",
            params={"view": self.config.view},
            paginator=_PAGER,
            cursor_field=field,
            client_side_filter=bool(field),
            on_request=with_formula if field else None,
            transform=_flatten,
        )


def _flatten(rec: dict[str, Any]) -> dict[str, Any]:
    return {**(rec.get("fields") or {}), "id": rec.get("id"), "createdTime": rec.get("createdTime")}
