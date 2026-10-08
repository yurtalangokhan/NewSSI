"""S3 source exercised through a fake boto3 client."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from connector import ConfiguredCatalog, Record, State, SyncMode, SyncState
from connector.sources.s3 import S3Source


class _Body:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


class _Paginator:
    def __init__(self, objects: dict[str, tuple[bytes, datetime]], page_size: int = 2) -> None:
        self._objects = objects
        self._page_size = page_size

    def paginate(self, Bucket: str, Prefix: str):  # noqa: N803
        keys = sorted(k for k in self._objects if k.startswith(Prefix))
        for i in range(0, len(keys), self._page_size):
            yield {
                "Contents": [
                    {
                        "Key": k,
                        "LastModified": self._objects[k][1],
                        "Size": len(self._objects[k][0]),
                    }
                    for k in keys[i : i + self._page_size]
                ]
            }


class _FakeS3:
    def __init__(self, objects: dict[str, tuple[bytes, datetime]], *, bucket_ok: bool = True):
        self._objects = objects
        self._bucket_ok = bucket_ok
        self.get_calls: list[str] = []

    def head_bucket(self, Bucket: str) -> dict[str, Any]:  # noqa: N803
        if not self._bucket_ok:
            raise RuntimeError("NoSuchBucket")
        return {}

    def get_paginator(self, name: str) -> _Paginator:
        assert name == "list_objects_v2"
        return _Paginator(self._objects)

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        self.get_calls.append(Key)
        return {"Body": _Body(self._objects[Key][0])}


T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 1, 2, tzinfo=UTC)
T3 = datetime(2026, 1, 3, tzinfo=UTC)

OBJECTS = {
    "data/orders/2026-01.csv": (b"id,total\n1,9.5\n2,3.0\n", T1),
    "data/orders/2026-02.csv": (b"id,total\n3,1.0\n", T3),
    "data/events/a.jsonl": (b'{"e": "x"}\n\n{"e": "y"}\n', T2),
    "data/events/b.json": (b'[{"e": "z"}, 42]', T2),
    "data/logo.png": (b"ignored", T1),
    "data/orders/": (b"", T1),  # folder marker
}


def _source(client: _FakeS3, **cfg: Any) -> S3Source:
    base = {"bucket": "b", "prefix": "data/"}
    return S3Source(S3Source.validate_config({**base, **cfg}), client=client)


async def test_check() -> None:
    assert (await _source(_FakeS3(OBJECTS)).check()).ok
    bad = await _source(_FakeS3(OBJECTS, bucket_ok=False)).check()
    assert not bad.ok and "NoSuchBucket" in (bad.message or "")


async def test_default_stream_reads_all_supported_formats() -> None:
    client = _FakeS3(OBJECTS)
    src = _source(client)
    catalog = await src.discover()
    assert catalog.names() == ["files"]
    assert catalog.get("files").default_cursor_field == ["_source_file_last_modified"]

    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    records = [i for i in items if isinstance(i, Record)]
    files = [r.data["_source_file"] for r in records]
    # ordered by (last_modified, key); txt and folder markers skipped
    assert files == [
        "data/orders/2026-01.csv",
        "data/orders/2026-01.csv",
        "data/events/a.jsonl",
        "data/events/a.jsonl",
        "data/events/b.json",
        "data/orders/2026-02.csv",
    ]
    assert records[0].data == {
        "id": "1",
        "total": "9.5",
        "_source_file": "data/orders/2026-01.csv",
        "_source_file_last_modified": T1.isoformat(),
    }
    assert [r.data["e"] for r in records if "e" in r.data] == ["x", "y", "z"]
    assert not any(isinstance(i, State) for i in items)  # full refresh -> no state
    assert "data/logo.png" not in client.get_calls


async def test_named_streams_with_globs_and_incremental() -> None:
    client = _FakeS3(OBJECTS)
    src = _source(
        client,
        streams=[
            {"name": "orders", "glob": "orders/*.csv"},
            {"name": "events", "glob": "events/**", "format": None},
        ],
    )
    catalog = await src.discover()
    assert catalog.names() == ["orders", "events"]
    assert set(catalog.get("orders").json_schema["properties"]) >= {"id", "total"}

    configured = ConfiguredCatalog.from_catalog(catalog, sync_mode=SyncMode.INCREMENTAL)
    prior = SyncState(streams={"orders": {"cursor": T1.isoformat()}})
    items = [i async for i in src.read(configured, prior)]
    orders = [i for i in items if isinstance(i, Record) and i.stream == "orders"]
    events = [i for i in items if isinstance(i, Record) and i.stream == "events"]
    assert [r.data["id"] for r in orders] == ["3"]  # only the file newer than the cursor
    assert len(events) == 3
    states = {s.stream: s.data["cursor"] for s in items if isinstance(s, State)}
    assert states == {"orders": T3.isoformat(), "events": T2.isoformat()}


async def test_incremental_reads_objects_written_in_the_cursor_second_later() -> None:
    # Object stores stamp whole seconds. An object written in the same second as the last
    # one read, after the listing was taken, carries the cursor's timestamp: the state names
    # the objects read at that timestamp so the next run reads only the new one.
    objects = {"data/a.jsonl": (b'{"e": "a"}\n', T2), "data/b.jsonl": (b'{"e": "b"}\n', T2)}
    src = _source(_FakeS3(objects))
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL
    )
    items = [i async for i in src.read(configured)]
    state = [i for i in items if isinstance(i, State)][-1].data
    assert state == {"cursor": T2.isoformat(), "keys_at_cursor": ["data/a.jsonl", "data/b.jsonl"]}

    objects["data/c.jsonl"] = (b'{"e": "c"}\n', T2)
    src = _source(_FakeS3(objects))
    items = [i async for i in src.read(configured, SyncState(streams={"files": state}))]
    assert [i.data["e"] for i in items if isinstance(i, Record)] == ["c"]
    state = [i for i in items if isinstance(i, State)][-1].data
    assert state["keys_at_cursor"] == ["data/a.jsonl", "data/b.jsonl", "data/c.jsonl"]

    # A state written before the keys were recorded skips the cursor second, as it did.
    legacy = SyncState(streams={"files": {"cursor": T2.isoformat()}})
    items = [i async for i in src.read(configured, legacy)]
    assert not any(isinstance(i, Record) for i in items)


async def test_max_file_size_and_unknown_stream_are_skipped() -> None:
    client = _FakeS3(OBJECTS)
    src = _source(client, max_file_size_bytes=10, streams=[{"name": "orders", "glob": "orders/*"}])
    catalog = await src.discover()
    records = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert records == []  # every csv exceeds 10 bytes
    assert client.get_calls == []  # discovery does not sample an object it would never read
    assert S3Source.validate_config({"bucket": "b"}).max_file_size_bytes == 50 * 1024 * 1024


async def test_discover_does_not_download_text_documents() -> None:
    # A text file's schema is known without reading it; the first object of a stream can be
    # a document of many megabytes, and discovery runs inside a UI request.
    client = _FakeS3({"data/a.md": (b"# Big" * 1000, T1), "data/b.csv": (b"id\n1\n", T2)})
    src = _source(
        client,
        streams=[{"name": "docs", "glob": "*.md"}, {"name": "rows", "glob": "*.csv"}],
    )
    catalog = await src.discover()
    assert catalog.get("docs").json_schema["properties"]["content"] == {"type": "string"}
    assert "id" in catalog.get("rows").json_schema["properties"]
    assert client.get_calls == ["data/b.csv"]


def test_secrets_and_schema() -> None:
    assert S3Source.secret_fields() == {
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
    }
    schema = S3Source.spec().connection_specification
    assert "streams" in schema["properties"] and "$defs" in schema


async def test_text_and_html_files_become_single_document_records() -> None:
    client = _FakeS3(
        {
            "docs/guide.md": (b"# Guide\n\nHello", T1),
            "docs/page.html": (b"<h1>Title</h1><p>Body &amp; more</p><script>x()</script>", T2),
        }
    )
    src = S3Source(S3Source.validate_config({"bucket": "b", "prefix": "docs/"}), client=client)
    catalog = await src.discover()
    records = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data["content"] for r in records] == ["# Guide\n\nHello", "Title\nBody & more"]
    assert records[1].data["_source_file"] == "docs/page.html"


async def test_tsv_files_are_split_on_tabs_unless_a_delimiter_is_configured() -> None:
    objects = {
        "data/cols.tsv": (b"id\tname\n1\talpha\n2\tbeta\n", T1),
        "data/semi.tsv": (b"id;name\n3;gamma\n", T2),
    }
    src = _source(_FakeS3(objects))  # default stream: the delimiter is left at ","
    catalog = await src.discover()
    assert {"id", "name"} <= set(catalog.get("files").json_schema["properties"])
    rows = [
        i.data
        async for i in src.read(ConfiguredCatalog.from_catalog(catalog))
        if isinstance(i, Record)
    ]
    tabs = [r for r in rows if r["_source_file"] == "data/cols.tsv"]
    assert [(r["id"], r["name"]) for r in tabs] == [("1", "alpha"), ("2", "beta")]

    semi = _source(
        _FakeS3(objects), streams=[{"name": "semi", "glob": "semi.tsv", "csv_delimiter": ";"}]
    )
    semi_catalog = await semi.discover()
    semi_rows = [
        i.data
        async for i in semi.read(ConfiguredCatalog.from_catalog(semi_catalog))
        if isinstance(i, Record)
    ]
    assert [(r["id"], r["name"]) for r in semi_rows] == [("3", "gamma")]  # configured: honoured
