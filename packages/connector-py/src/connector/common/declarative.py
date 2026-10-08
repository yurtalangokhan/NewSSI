"""Declarative REST sources.

Most SaaS APIs differ only in *data*: which endpoints exist, where the record
list sits in the response, how the next page is requested and which parameter
filters by modification time. :class:`DeclarativeRestSource` implements
``discover`` / ``read`` / ``check`` once; a connector describes its API as a list
of :class:`StreamSpec` objects and picks a :class:`Paginator` strategy.

Adding a connector therefore means adding a small class (open/closed), and a
new pagination style means adding one ``Paginator`` subclass that every
connector can reuse.

Paginators are stateless: everything they need lives in the
:class:`PageRequest` they receive, so a single instance can be shared by all
streams and all concurrent syncs.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, TypeVar

import httpx
from pydantic import BaseModel

from ..errors import SourceError
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
    utcnow,
)
from .cursor import held_back, is_newer, later
from .rest_source import RestSource, parse_iso, split_query

logger = logging.getLogger("connector.declarative")

ConfigT = TypeVar("ConfigT", bound=BaseModel)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def dig(payload: Any, path: str | None) -> Any:
    """Follow a dot path (``a.b.0.c``) through dicts and lists; ``None`` if absent."""
    if not path:
        return payload
    node = payload
    for part in path.split("."):
        if isinstance(node, Mapping):
            node = node.get(part)
        elif isinstance(node, list) and part.lstrip("-").isdigit():
            idx = int(part)
            node = node[idx] if -len(node) <= idx < len(node) else None
        else:
            return None
        if node is None:
            return None
    return node


def as_iso(value: Any) -> str:
    parsed = parse_iso(value)
    return parsed.isoformat() if parsed else str(value)


def as_iso_z(value: Any) -> str:
    parsed = parse_iso(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed else str(value)


def as_epoch_seconds(value: Any) -> int:
    parsed = parse_iso(value)
    return int(parsed.timestamp()) if parsed else int(float(value))


def as_epoch_millis(value: Any) -> int:
    parsed = parse_iso(value)
    return int(parsed.timestamp() * 1000) if parsed else int(float(value))


def from_epoch_seconds(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def from_epoch_millis(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# pagination strategies
# ---------------------------------------------------------------------------


@dataclass
class PageRequest:
    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def target(self, in_body: bool) -> dict[str, Any]:
        if in_body:
            if self.body is None:
                self.body = {}
            return self.body
        return self.params


class Paginator:
    """No pagination. Subclasses mutate and return the request for the next page."""

    def start(self, req: PageRequest) -> None:
        """Add first-page parameters (page size etc.)."""

    def next(
        self, req: PageRequest, response: httpx.Response, payload: Any, records: list[Any]
    ) -> PageRequest | None:
        return None


@dataclass(frozen=True)
class OffsetPagination(Paginator):
    """``?limit=100&offset=200``. Stops on an empty page or when ``total_path`` is reached."""

    limit_param: str = "limit"
    offset_param: str = "offset"
    page_size: int = 100
    in_body: bool = False
    total_path: str | None = None
    stop_on_short_page: bool = True

    def start(self, req: PageRequest) -> None:
        tgt = req.target(self.in_body)
        tgt[self.limit_param] = self.page_size
        tgt.setdefault(self.offset_param, 0)

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if not records or (self.stop_on_short_page and len(records) < self.page_size):
            return None
        tgt = req.target(self.in_body)
        offset = int(tgt.get(self.offset_param, 0)) + len(records)
        total = dig(payload, self.total_path) if self.total_path else None
        if total is not None and offset >= int(total):
            return None
        tgt[self.offset_param] = offset
        return req


@dataclass(frozen=True)
class PageNumberPagination(Paginator):
    """``?page=2&per_page=100``. Stops on an empty page or at ``last_page_path``."""

    page_param: str = "page"
    size_param: str | None = "per_page"
    page_size: int = 100
    first_page: int = 1
    in_body: bool = False
    last_page_path: str | None = None
    has_more_path: str | None = None
    stop_on_short_page: bool = True

    def start(self, req: PageRequest) -> None:
        tgt = req.target(self.in_body)
        tgt.setdefault(self.page_param, self.first_page)
        if self.size_param:
            tgt[self.size_param] = self.page_size

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if not records:
            return None
        if self.stop_on_short_page and self.size_param and len(records) < self.page_size:
            return None
        tgt = req.target(self.in_body)
        page = int(tgt.get(self.page_param, self.first_page))
        if self.last_page_path:
            last = dig(payload, self.last_page_path)
            if last is True or (
                isinstance(last, int | float) and not isinstance(last, bool) and page >= last
            ):
                return None
        if self.has_more_path and not dig(payload, self.has_more_path):
            return None
        tgt[self.page_param] = page + 1
        return req


@dataclass(frozen=True)
class CursorPagination(Paginator):
    """Opaque cursor taken from the response body and sent back as a parameter."""

    cursor_path: str = "next_cursor"
    cursor_param: str = "cursor"
    in_body: bool = False
    size_param: str | None = None
    page_size: int = 100
    has_more_path: str | None = None

    def start(self, req: PageRequest) -> None:
        if self.size_param:
            req.target(self.in_body)[self.size_param] = self.page_size

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        cursor = dig(payload, self.cursor_path)
        if cursor in (None, "", 0):
            return None
        if self.has_more_path and not dig(payload, self.has_more_path):
            return None
        req.target(self.in_body)[self.cursor_param] = cursor
        return req


@dataclass(frozen=True)
class LastRecordPagination(Paginator):
    """Next page starts after a field of the last record (``starting_after``, ``before``...)."""

    param: str = "starting_after"
    record_field: str = "id"
    size_param: str | None = "limit"
    page_size: int = 100
    in_body: bool = False
    offset: int = 0
    """Added to numeric values (``-1`` for exclusive ``before=`` style APIs)."""
    stop_on_short_page: bool = True

    def start(self, req: PageRequest) -> None:
        if self.size_param:
            req.target(self.in_body)[self.size_param] = self.page_size

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if not records or not isinstance(records[-1], Mapping):
            return None
        if self.stop_on_short_page and self.size_param and len(records) < self.page_size:
            return None
        value = dig(records[-1], self.record_field)
        if value is None:
            return None
        if self.offset and isinstance(value, int | float):
            value = value + self.offset
        tgt = req.target(self.in_body)
        if tgt.get(self.param) == value:
            return None
        tgt[self.param] = value
        return req


@dataclass(frozen=True)
class ContinueParamsPagination(Paginator):
    """The response holds a dict of parameters to merge into the next request (MediaWiki)."""

    continue_path: str = "continue"

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        token = dig(payload, self.continue_path)
        if not isinstance(token, Mapping) or not token:
            return None
        # MediaWiki drops a sub-query's ``*continue`` once it is exhausted; left in the request
        # it would be applied again to the next generator page.
        for key in [k for k in req.params if k.endswith("continue") and k not in token]:
            del req.params[key]
        req.params.update(token)
        return req


@dataclass(frozen=True)
class NextUrlPagination(Paginator):
    """The response carries the full URL of the next page (``links.next``, ``@odata.nextLink``)."""

    next_url_path: str = "next"
    size_param: str | None = None
    page_size: int = 100

    def start(self, req: PageRequest) -> None:
        if self.size_param:
            req.params[self.size_param] = self.page_size

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        url = dig(payload, self.next_url_path)
        if not url or not isinstance(url, str):
            return None
        return PageRequest(
            method=req.method, url=url, params={}, body=req.body, headers=req.headers
        )


@dataclass(frozen=True)
class LinkHeaderPagination(Paginator):
    """RFC 5988 ``Link: <...>; rel="next"`` (GitHub, Canvas, Guru)."""

    size_param: str | None = "per_page"
    page_size: int = 100

    def start(self, req: PageRequest) -> None:
        if self.size_param:
            req.params[self.size_param] = self.page_size

    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        nxt = response.links.get("next", {}).get("url")
        if not nxt:
            return None
        return PageRequest(
            method=req.method, url=nxt, params={}, body=req.body, headers=req.headers
        )


# ---------------------------------------------------------------------------
# stream description
# ---------------------------------------------------------------------------

RequestHook = Callable[[PageRequest, Any], None]
RecordTransform = Callable[[dict[str, Any]], dict[str, Any] | None]
RecordExpand = Callable[[dict[str, Any]], Iterable[dict[str, Any]]]
ErrorCheck = Callable[[Any], str | None]
CursorLookup = Callable[[dict[str, Any] | None], Any]


def _no_cursor(parent: dict[str, Any] | None) -> Any:
    return None


_PARENT_FIELD = re.compile(r"\{parent\[([^\]]+)\]")


class _ParentReads:
    """Parent streams during one ``read()``: which are shared by several configured
    children (kept for the siblings, cut down to the fields they refer to) and when
    the kept records can go. A parent with one child is never kept."""

    def __init__(self, specs: Mapping[str, StreamSpec], catalog: ConfiguredCatalog) -> None:
        children: dict[str, list[StreamSpec]] = {}
        for configured in catalog.streams:
            spec = specs.get(configured.stream.name)
            if spec is not None and spec.parent is not None and not spec.parent_uses_cursor:
                children.setdefault(spec.parent, []).append(spec)
        self._pending = {parent: len(kids) for parent, kids in children.items()}
        self._fields = {parent: _parent_fields_used(kids) for parent, kids in children.items()}
        self._kept: dict[str, list[dict[str, Any]]] = {}

    def cached(self, parent: str) -> list[dict[str, Any]] | None:
        return self._kept.get(parent)

    def keep(self, parent: str) -> list[dict[str, Any]] | None:
        """The list to fill while reading ``parent``, when another child still needs it."""
        if self._pending.get(parent, 0) < 2:
            return None
        return self._kept.setdefault(parent, [])

    def project(self, parent: str, record: dict[str, Any]) -> dict[str, Any]:
        fields = self._fields.get(parent)
        if fields is None:
            return record
        return {k: v for k, v in record.items() if k in fields}

    def done(self, spec: StreamSpec) -> None:
        """Child ``spec`` is read: its parent's records go once no sibling is left."""
        if spec.parent is None or spec.parent_uses_cursor:
            return
        self._pending[spec.parent] = self._pending.get(spec.parent, 1) - 1
        if self._pending[spec.parent] <= 0:
            self._kept.pop(spec.parent, None)


def _parent_fields_used(children: list[StreamSpec]) -> set[str] | None:
    """Top-level parent fields the child specs refer to; ``None`` when one of them gets
    the whole parent record (``enrich``) and nothing can be dropped."""
    fields: set[str] = set()
    for spec in children:
        if spec.enrich is not None:
            return None
        fields.add(spec.parent_key.split(".", 1)[0])
        for text in (spec.path, spec.detail_path or ""):
            fields.update(m.split(".", 1)[0] for m in _PARENT_FIELD.findall(text))
    return fields


@dataclass(frozen=True)
class StreamSpec:
    """One endpoint exposed as a stream."""

    name: str
    path: str
    """URL or path. ``{parent[field]}`` is filled from the parent record."""
    method: str = "GET"
    records_path: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    body: Mapping[str, Any] | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    paginator: Paginator = field(default_factory=Paginator)
    primary_key: tuple[str, ...] = ("id",)

    # incremental
    cursor_field: str | None = None
    """Dot path of the record's modification marker; enables incremental sync."""
    incremental_param: str | None = None
    """Request parameter that receives the stored cursor (server-side filter)."""
    incremental_in_body: bool = False
    cursor_format: Callable[[Any], Any] = as_iso
    client_side_filter: bool = False
    """Drop records not newer than the cursor (for APIs that cannot filter)."""
    stop_when_page_seen: bool = False
    """With ``client_side_filter``, for a list the API orders by the cursor field newest
    first: stop paging at the first page whose records are all older than the cursor.
    Only exact when the order *is* the cursor field (not for a list ordered by id whose
    cursor is a modification stamp: an old item edited later would be missed)."""
    on_request: RequestHook | None = None
    """Last-word hook ``(request, cursor)`` for APIs with unusual filter syntax."""

    # parent / child
    parent: str | None = None
    parent_field: str | None = None
    """Copy the parent's ``parent_key`` into every child record under this name."""
    parent_key: str = "id"
    skip_statuses: tuple[int, ...] = (403, 404)
    """For child streams: skip a parent whose request fails with one of these."""
    per_parent_cursor: bool = False
    """Track the incremental cursor per parent record (channels, projects). Avoids
    losing records written to one parent while another was being read. Only for
    parents that are few in number: the map is stored in the sync state."""
    parent_uses_cursor: bool = False
    """Read the parents with this stream's cursor (their own ``incremental_param`` or
    client-side filter) instead of all of them. For APIs where a child changes its
    parent's modification marker (a comment moves its ticket's ``updated_at``), an
    incremental run then visits only the parents that gained children."""

    # per-record detail request (list endpoints that omit the body)
    detail_path: str | None = None
    detail_params: Mapping[str, Any] = field(default_factory=dict)
    detail_records_path: str | None = None
    detail_key: str | None = None
    """Store the detail under this key instead of merging it into the record."""

    expand: RecordExpand | None = None
    """Turn one listed item into several records (nested trees, grouped results)."""
    enrich: str | None = None
    """Name of an async source method ``(record, parent) -> record | None`` run per record."""
    transform: RecordTransform | None = None
    error_check: ErrorCheck | None = None
    schema: Mapping[str, Any] = field(default_factory=dict)


class _CursorTracker:
    """Incremental bookkeeping for one stream: global cursor plus optional per-parent map."""

    def __init__(self, spec: StreamSpec, saved: Mapping[str, Any], *, enabled: bool) -> None:
        self.spec = spec
        self.started = utcnow()
        self.last = saved.get("cursor") if enabled else None
        self.max_seen = self.last
        self.per_parent = enabled and spec.per_parent_cursor and spec.parent is not None
        self.by_parent: dict[str, Any] = (
            dict(saved.get("by_parent") or {}) if self.per_parent else {}
        )
        self._staged: dict[str, Any] = {}

    def _key(self, parent: dict[str, Any]) -> str:
        return str(dig(parent, self.spec.parent_key))

    def cursor_for(self, parent: dict[str, Any] | None) -> Any:
        if not self.per_parent or parent is None:
            return self.last
        return self.by_parent.get(self._key(parent))

    def accept(self, parent: dict[str, Any] | None, rec: dict[str, Any]) -> bool:
        value = dig(rec, self.spec.cursor_field)
        floor = self.cursor_for(parent)
        if self.spec.client_side_filter and floor is not None and not is_newer(value, floor):
            return False
        self.max_seen = later(self.max_seen, value)
        if self.per_parent and parent is not None:
            key = self._key(parent)
            # Staged, not applied: the floor for this parent must stay fixed while reading.
            self._staged[key] = later(self._staged.get(key, self.by_parent.get(key)), value)
        return True

    def state(self) -> dict[str, Any]:
        # Pages arrive in no particular order: the cursor is held back (see ``held_back``).
        data: dict[str, Any] = {"cursor": held_back(self.max_seen, self.last, self.started)}
        if self.per_parent:
            data["by_parent"] = {
                key: held_back(value, self.by_parent.get(key), self.started)
                for key, value in {**self.by_parent, **self._staged}.items()
            }
        return data


class DeclarativeRestSource(RestSource[ConfigT]):
    """A :class:`RestSource` driven by :class:`StreamSpec` definitions."""

    max_pages_per_stream: ClassVar[int] = 100_000

    def streams(self) -> list[StreamSpec]:
        """Stream definitions. Instance method so they can depend on ``self.config``."""
        raise NotImplementedError

    async def stream_specs(self) -> list[StreamSpec]:
        """Async variant for APIs whose streams must be discovered (tables, objects)."""
        return self.streams()

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- connector API -----------------------------------------------------------

    async def check(self) -> CheckResult:
        """Fetch the first page of the first top-level stream."""
        try:
            specs = await self.stream_specs()
            spec = next((s for s in specs if s.parent is None), None)
            if spec is None:
                return CheckResult(ok=True)
            req = self._build_request(spec, None, None)
            await self._fetch_page(spec, req)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        streams = []
        for spec in await self.stream_specs():
            incremental = spec.cursor_field is not None
            streams.append(
                Stream(
                    name=spec.name,
                    json_schema={"type": "object", "properties": dict(spec.schema)},
                    supported_sync_modes=[SyncMode.FULL_REFRESH]
                    + ([SyncMode.INCREMENTAL] if incremental else []),
                    source_defined_cursor=incremental,
                    default_cursor_field=[spec.cursor_field] if spec.cursor_field else [],
                    source_defined_primary_key=[[k] for k in spec.primary_key],
                )
            )
        return Catalog(streams=streams)

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        specs = {s.name: s for s in await self.stream_specs()}
        parents = _ParentReads(specs, catalog)
        for configured in catalog.streams:
            spec = specs.get(configured.stream.name)
            if spec is None:
                continue
            incremental = (
                configured.sync_mode is SyncMode.INCREMENTAL and spec.cursor_field is not None
            )
            saved = state.get(spec.name) if incremental else {}
            tracker = _CursorTracker(spec, saved, enabled=incremental)
            async for parent, rec in self._read_stream(spec, specs, tracker.cursor_for, parents):
                if incremental and not tracker.accept(parent, rec):
                    continue
                yield Record(stream=spec.name, data=rec)
            if incremental and tracker.max_seen is not None:
                yield State(stream=spec.name, data=tracker.state())
            parents.done(spec)

    # ---- engine ---------------------------------------------------------------------

    async def _read_stream(
        self,
        spec: StreamSpec,
        specs: Mapping[str, StreamSpec],
        cursor_for: CursorLookup,
        parents: _ParentReads,
    ) -> AsyncIterator[tuple[dict[str, Any] | None, dict[str, Any]]]:
        """Yield ``(parent, record)``; ``parent`` is ``None`` for top-level streams."""
        if spec.parent is None:
            async for rec in self._read_records(spec, cursor_for(None)):
                yield None, rec
            return
        async for parent in self._parents_of(spec, specs, cursor_for, parents):
            try:
                async for rec in self._read_pages(spec, parent, cursor_for(parent)):
                    if spec.parent_field:
                        rec.setdefault(spec.parent_field, dig(parent, spec.parent_key))
                    yield parent, rec
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in spec.skip_statuses:
                    raise
                logger.warning(
                    "%s: skipping %s=%s (%s)",
                    spec.name,
                    spec.parent,
                    dig(parent, spec.parent_key),
                    exc.response.status_code,
                )
            except _ApiError as exc:
                logger.warning(
                    "%s: skipping %s=%s (%s)",
                    spec.name,
                    spec.parent,
                    dig(parent, spec.parent_key),
                    exc,
                )

    async def _parents_of(
        self,
        spec: StreamSpec,
        specs: Mapping[str, StreamSpec],
        cursor_for: CursorLookup,
        parents: _ParentReads,
    ) -> AsyncIterator[dict[str, Any]]:
        """The parent records of child stream ``spec``.

        Read with the child's cursor when ``parent_uses_cursor`` says so. Streamed,
        page by page, when this is the only configured child of the parent; kept
        for the siblings otherwise, cut down to the fields the children refer to, so
        a parent stream of any size costs one page of memory - or that projection.
        """
        assert spec.parent is not None
        parent_spec = specs[spec.parent]
        if spec.parent_uses_cursor:
            cursor = cursor_for(None)
            async for _, parent in self._read_stream(
                parent_spec, specs, lambda _p: cursor, parents
            ):
                yield parent
            return
        kept = parents.cached(spec.parent)
        if kept is not None:
            for parent in kept:
                yield parent
            return
        keep = parents.keep(spec.parent)
        async for _, parent in self._read_stream(parent_spec, specs, _no_cursor, parents):
            if keep is not None:
                parent = parents.project(spec.parent, parent)
                keep.append(parent)
            yield parent

    async def _read_records(self, spec: StreamSpec, cursor: Any) -> AsyncIterator[dict[str, Any]]:
        """Records of a top-level stream. Override to fan one stream out over several
        request series (folder walks, category lists)."""
        async for rec in self._read_pages(spec, None, cursor):
            yield rec

    async def _read_pages(
        self, spec: StreamSpec, parent: dict[str, Any] | None, cursor: Any
    ) -> AsyncIterator[dict[str, Any]]:
        req: PageRequest | None = self._build_request(spec, parent, cursor)
        previous: str | None = None
        for _ in range(self.max_pages_per_stream):
            if req is None:
                return
            response, payload, records = await self._fetch_page(spec, req)
            signature = page_signature(records)
            if records and signature == previous:
                # The API ignored the paging parameters and served the same page again.
                logger.warning("%s: page repeated, stopping pagination at %s", spec.name, req.url)
                return
            previous = signature
            page_seen = bool(records)
            for raw in records:
                if not isinstance(raw, Mapping):
                    continue
                for item in spec.expand(dict(raw)) if spec.expand else (dict(raw),):
                    listed: dict[str, Any] = dict(item)
                    if self._already_seen(spec, listed, cursor):
                        continue  # skip before paying for detail / enrich requests
                    page_seen = False
                    rec = await self._complete(spec, listed, parent)
                    if rec is not None and spec.transform is not None:
                        rec = spec.transform(rec)
                    if rec is not None:
                        yield rec
            if page_seen and spec.stop_when_page_seen and cursor is not None:
                return  # newest first: everything after this page is older still
            req = spec.paginator.next(req, response, payload, records)

    async def _complete(
        self, spec: StreamSpec, listed: dict[str, Any], parent: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """The listed item with its detail and ``enrich`` applied; ``None`` for an item
        whose per-record requests answer one of ``skip_statuses`` (deleted meanwhile,
        no access): that record is skipped, not the rest of the page."""
        try:
            rec: dict[str, Any] | None = listed
            if spec.detail_path:
                rec = await self._with_detail(spec, listed, parent)
            if spec.enrich and rec is not None:
                rec = await getattr(self, spec.enrich)(rec, parent)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in spec.skip_statuses:
                raise
            logger.warning(
                "%s: skipping record %s (%s)",
                spec.name,
                dig(listed, spec.primary_key[0]) if spec.primary_key else "?",
                exc.response.status_code,
            )
            return None
        return rec

    def _already_seen(self, spec: StreamSpec, rec: Mapping[str, Any], cursor: Any) -> bool:
        """Early client-side filter. Undecidable (cursor computed by ``transform``) means keep.

        A subclass whose listed items are not all records (folders in a file tree)
        overrides this to keep what the filter must not judge."""
        if not spec.client_side_filter or cursor is None or not spec.cursor_field:
            return False
        value = dig(rec, spec.cursor_field)
        return value is not None and not is_newer(value, cursor)

    def _build_request(
        self, spec: StreamSpec, parent: dict[str, Any] | None, cursor: Any
    ) -> PageRequest:
        req = PageRequest(
            method=spec.method,
            url=spec.path.format(parent=parent or {}, config=self.config),
            params={k: v for k, v in spec.params.items() if v is not None},
            body=dict(spec.body) if spec.body is not None else None,
            headers=dict(spec.headers),
        )
        spec.paginator.start(req)
        if cursor is not None and spec.incremental_param:
            req.target(spec.incremental_in_body)[spec.incremental_param] = spec.cursor_format(
                cursor
            )
        if spec.on_request is not None:
            spec.on_request(req, cursor)
        return req

    async def _fetch_page(
        self, spec: StreamSpec, req: PageRequest
    ) -> tuple[httpx.Response, Any, list[Any]]:
        url, params = split_query(req.url, req.params)
        response = await self.request(
            req.method,
            url,
            params=params or None,
            json=req.body if req.method != "GET" else None,
            headers=req.headers or None,
        )
        payload = response.json() if response.content else None
        if spec.error_check is not None:
            error = spec.error_check(payload)
            if error:
                raise _ApiError(error)
        node = payload if isinstance(payload, list) else dig(payload, spec.records_path)
        if node is None:
            records: list[Any] = []
        elif isinstance(node, list):
            records = node
        else:
            records = [node]
        return response, payload, records

    async def _with_detail(
        self, spec: StreamSpec, rec: dict[str, Any], parent: dict[str, Any] | None
    ) -> dict[str, Any]:
        assert spec.detail_path is not None
        url = spec.detail_path.format(record=rec, parent=parent or {}, config=self.config)
        payload = await self.get_json(url, params=dict(spec.detail_params) or None)
        detail = dig(payload, spec.detail_records_path)
        if spec.detail_key:
            rec[spec.detail_key] = detail
        elif isinstance(detail, Mapping):
            rec = {**rec, **detail}
        return rec


def page_signature(records: list[Any]) -> str:
    """Cheap fingerprint of a page: size plus its first and last record."""
    if not records:
        return "empty"
    return f"{len(records)}|{records[0]!r}|{records[-1]!r}"


class _ApiError(SourceError):
    """The API answered 200 but reported an application-level error."""
