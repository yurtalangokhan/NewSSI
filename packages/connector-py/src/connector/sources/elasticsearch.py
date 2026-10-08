"""Elasticsearch source: every index (or the configured ones) as a stream.

Talks to the REST API directly, without a client library. Documents are read
with the scroll API, which behaves the same on Elasticsearch 6-8 and
OpenSearch and exists for exactly this job: walking a whole index in order.
Incremental sync adds a ``range`` filter on the index's cursor field
(``@timestamp``, ``updated_at`` ...) and remembers the highest value seen.

Auth: basic (``username`` / ``password``) or an API key. The key may be given
as the base64 value Elasticsearch shows on creation or as plain ``id:api_key``.
"""

from __future__ import annotations

import base64
import contextlib
from collections.abc import AsyncIterator, Mapping
from typing import Any, ClassVar, TypeVar

import httpx
from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.cursor import CursorTracker, incremental_cursor
from ..common.declarative import dig
from ..common.rest_source import RestSource, basic_auth_header, parse_iso
from ..errors import ConnectorError
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

_ES_TO_JSON: dict[str, dict[str, Any]] = {
    "long": {"type": "integer"},
    "integer": {"type": "integer"},
    "short": {"type": "integer"},
    "byte": {"type": "integer"},
    "unsigned_long": {"type": "integer"},
    "double": {"type": "number"},
    "float": {"type": "number"},
    "half_float": {"type": "number"},
    "scaled_float": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date-time"},
    "date_nanos": {"type": "string", "format": "date-time"},
    "nested": {"type": "array"},
    "object": {"type": "object"},
    "flattened": {"type": "object"},
}


class SearchIndexOptions(BaseModel):
    """What to read and how; shared by the Elasticsearch and OpenSearch configs."""

    url: str = Field(description="Cluster URL, e.g. https://search.acme.com:9200")
    indices: list[str] | None = Field(
        default=None,
        description="Index names or patterns (orders-*). Default: every open, non-system index.",
    )
    cursor_field: str | None = Field(
        default=None,
        description="Modification-time field enabling incremental sync on indices that have it, "
        "e.g. '@timestamp' or 'updated_at'.",
    )
    cursor_fields: dict[str, str] = Field(
        default_factory=dict, description="index -> cursor field, overriding cursor_field."
    )
    query: dict[str, Any] | None = Field(
        default=None, description="Extra Query DSL clause AND-ed into every search."
    )
    include_fields: list[str] | None = Field(default=None, description="_source includes.")
    exclude_fields: list[str] | None = Field(default=None, description="_source excludes.")
    include_system_indices: bool = False
    page_size: int = Field(default=1000, ge=1, le=10_000)
    scroll_keep_alive: str = "5m"
    timeout_seconds: float = 60.0
    verify_ssl: bool = True


class ElasticsearchConfig(SearchIndexOptions):
    username: str | None = None
    password: str | None = secret_field(default=None)
    api_key: str | None = secret_field(
        default=None, description="API key: the base64 value Elasticsearch shows, or 'id:api_key'."
    )


SearchConfigT = TypeVar("SearchConfigT", bound=SearchIndexOptions)


class ElasticsearchSource(RestSource[SearchConfigT]):
    definition = ConnectorDefinition(
        name="elasticsearch",
        display_name="Elasticsearch",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SEARCH_ENGINE,
        documentation_url="https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-apis.html",
        icon="elasticsearch.svg",
        tags=frozenset({"search", "index", "self-hosted"}),
    )
    Config: ClassVar[type[BaseModel]] = ElasticsearchConfig
    check_path: ClassVar[str] = "/"

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def base_url(self) -> str:
        return self.config.url

    def auth_headers(self) -> dict[str, str]:
        api_key = getattr(self.config, "api_key", None)
        if api_key:
            token = base64.b64encode(api_key.encode()).decode() if ":" in api_key else api_key
            return {"Authorization": f"ApiKey {token}"}
        username = getattr(self.config, "username", None)
        if username:
            return basic_auth_header(username, getattr(self.config, "password", None) or "")
        return {}

    # ---- catalog -------------------------------------------------------------------

    async def discover(self) -> Catalog:
        expr = ",".join(self.config.indices) if self.config.indices else "*"
        mappings = await self.get_json(
            f"/{expr}/_mapping",
            params={
                "ignore_unavailable": "true",
                "allow_no_indices": "true",
                "expand_wildcards": "open",
            },
        )
        streams: list[Stream] = []
        for index in sorted(mappings or {}):
            if index.startswith(".") and not self.config.include_system_indices:
                continue
            props = _properties(mappings[index])
            cursor = self._cursor_for(index, props)
            streams.append(
                Stream(
                    name=index,
                    json_schema={
                        "type": "object",
                        "properties": {**_json_schema(props), **_HIT_FIELDS},
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH]
                    + ([SyncMode.INCREMENTAL] if cursor else []),
                    source_defined_cursor=bool(cursor),
                    default_cursor_field=[cursor] if cursor else [],
                    source_defined_primary_key=[["_id"]],
                )
            )
        return Catalog(streams=streams)

    def _cursor_for(self, index: str, props: Mapping[str, Any]) -> str | None:
        explicit = self.config.cursor_fields.get(index)
        if explicit:
            return explicit
        if self.config.cursor_field and _has_field(props, self.config.cursor_field):
            return self.config.cursor_field
        return None

    # ---- read ------------------------------------------------------------------------

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        for configured in catalog.streams:
            index = configured.stream.name
            cursor = incremental_cursor(configured)
            tracker = CursorTracker(index, state, enabled=cursor is not None)
            body = self._search_body(cursor, tracker.start)
            async for hit in self._scroll(index, body):
                source = hit.get("_source") or {}
                record = {**source, "_id": hit.get("_id"), "_index": hit.get("_index", index)}
                if cursor:
                    tracker.observe(dig(source, cursor))
                yield Record(stream=index, data=record)
            if final := tracker.final_state():
                yield final

    def _search_body(self, cursor: str | None, last: Any) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if self.config.query:
            filters.append(self.config.query)
        if cursor and last is not None:
            bound: dict[str, Any] = {"gt": last}
            if parse_iso(last) is not None:
                # The stored cursor is normalised ISO-8601 (see ``later``); the index may
                # map the field with another date format, so say how to read the bound.
                bound["format"] = "strict_date_optional_time||epoch_millis"
            filters.append({"range": {cursor: bound}})
        body: dict[str, Any] = {
            "size": self.config.page_size,
            "sort": ["_doc"],
            "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
        }
        if self.config.include_fields or self.config.exclude_fields:
            body["_source"] = {
                k: v
                for k, v in (
                    ("includes", self.config.include_fields),
                    ("excludes", self.config.exclude_fields),
                )
                if v
            }
        return body

    async def _scroll(self, index: str, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        keep = self.config.scroll_keep_alive
        page = await self.post_json(f"/{index}/_search", body, params={"scroll": keep})
        scroll_id = (page or {}).get("_scroll_id")
        try:
            while True:
                hits = ((page or {}).get("hits") or {}).get("hits") or []
                if not hits:
                    return
                for hit in hits:
                    yield hit
                if not scroll_id:
                    return
                page = await self.post_json(
                    "/_search/scroll", {"scroll": keep, "scroll_id": scroll_id}
                )
                scroll_id = (page or {}).get("_scroll_id") or scroll_id
        finally:
            if scroll_id:
                with contextlib.suppress(httpx.HTTPError, ConnectorError):
                    await self.request("DELETE", "/_search/scroll", json={"scroll_id": [scroll_id]})


def _properties(index_mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Field definitions of an index; tolerates the typed layout of Elasticsearch 6."""
    mappings = index_mapping.get("mappings") or {}
    if "properties" in mappings:
        return dict(mappings["properties"] or {})
    for value in mappings.values():  # {"_doc": {"properties": ...}}
        if isinstance(value, Mapping) and "properties" in value:
            return dict(value["properties"] or {})
    return {}


# ``read`` adds these to every hit, so every stream declares them.
_HIT_FIELDS: dict[str, dict[str, Any]] = {"_id": {"type": "string"}, "_index": {"type": "string"}}


def _json_schema(props: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, definition in props.items():
        if not isinstance(definition, Mapping):
            continue
        if "properties" in definition:
            inner = {"type": "object", "properties": _json_schema(definition["properties"])}
            nested = definition.get("type") == "nested"  # an array of such objects in every hit
            out[name] = {"type": "array", "items": inner} if nested else inner
            continue
        out[name] = dict(_ES_TO_JSON.get(str(definition.get("type", "")), {"type": "string"}))
    return out


def _has_field(props: Mapping[str, Any], path: str) -> bool:
    node: Any = props
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part].get("properties") if isinstance(node[part], Mapping) else None
        if node is None:
            node = {}
    return True
