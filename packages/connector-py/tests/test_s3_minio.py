"""MinIO source plus S3/MinIO destinations, exercised through a fake boto3 client."""

from __future__ import annotations

import gzip
import io
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from connector import (
    Batch,
    ConfiguredCatalog,
    ConfigValidationError,
    Connection,
    ConnectorCategory,
    ConnectorKind,
    ConnectorRegistry,
    DestinationSyncMode,
    JobStatus,
    Record,
    SyncOptions,
    SyncRunner,
)
from connector.common.s3_connection import AwsConnection, MinioConnection
from connector.destinations.minio import MinioDestination
from connector.destinations.s3 import S3Destination
from connector.sources.minio import MinioSource
from connector.sources.s3 import S3Source
from tests.conftest import FakeSource


class _Body:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


class FakeS3:
    """In-memory bucket implementing the boto3 calls the connectors use."""

    def __init__(self, objects: dict[str, bytes] | None = None, *, bucket_ok: bool = True) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.modified: dict[str, datetime] = dict.fromkeys(
            self.objects, datetime(2026, 1, 1, tzinfo=UTC)
        )
        self.content_types: dict[str, str] = {}
        self.bucket_ok = bucket_ok
        self.delete_calls: list[list[str]] = []

    def head_bucket(self, Bucket: str) -> dict[str, Any]:  # noqa: N803
        if not self.bucket_ok:
            raise RuntimeError("NoSuchBucket")
        return {}

    def get_paginator(self, name: str):  # noqa: ANN201
        assert name == "list_objects_v2"
        fake = self

        class _P:
            def paginate(self, Bucket: str, Prefix: str):  # noqa: N803, ANN202
                keys = sorted(k for k in fake.objects if k.startswith(Prefix))
                for i in range(0, max(len(keys), 1), 2):
                    yield {
                        "Contents": [
                            {
                                "Key": k,
                                "LastModified": fake.modified[k],
                                "Size": len(fake.objects[k]),
                            }
                            for k in keys[i : i + 2]
                        ]
                    }

        return _P()

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        return {"Body": _Body(self.objects[Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> dict[str, Any]:  # noqa: N803
        self.objects[Key] = Body
        self.modified[Key] = datetime.now(UTC)
        self.content_types[Key] = ContentType
        return {}

    def delete_objects(self, Bucket: str, Delete: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        keys = [o["Key"] for o in Delete["Objects"]]
        self.delete_calls.append(keys)
        for k in keys:
            self.objects.pop(k, None)
            self.modified.pop(k, None)
        return {}


MINIO = {"endpoint": "minio:9000", "access_key": "ak", "secret_key": "sk", "bucket": "b"}


# ---------------------------------------------------------------------------
# connection mixins
# ---------------------------------------------------------------------------


def test_minio_connection_builds_path_style_kwargs() -> None:
    plain = MinioConnection(endpoint="minio:9000", access_key="a", secret_key="s")
    assert plain.endpoint_url() == "http://minio:9000"
    kwargs = plain.client_kwargs()
    assert kwargs["path_style"] is True and kwargs["region_name"] == "us-east-1"
    assert kwargs["aws_access_key_id"] == "a" and kwargs["aws_secret_access_key"] == "s"

    tls = MinioConnection(endpoint="minio.acme.com", access_key="a", secret_key="s", secure=True)
    assert tls.endpoint_url() == "https://minio.acme.com"
    full = MinioConnection(endpoint="https://minio.acme.com:9443/", access_key="a", secret_key="s")
    assert full.endpoint_url() == "https://minio.acme.com:9443"


def test_aws_connection_kwargs_have_no_path_style() -> None:
    kwargs = AwsConnection(region="eu-west-1").client_kwargs()
    assert kwargs["region_name"] == "eu-west-1" and "path_style" not in kwargs


# ---------------------------------------------------------------------------
# MinIO source
# ---------------------------------------------------------------------------


async def test_minio_source_reuses_s3_reader() -> None:
    client = FakeS3({"in/users.jsonl": b'{"id": 1}\n{"id": 2}\n', "in/skip.bin": b"x"})
    cfg = MinioSource.validate_config({**MINIO, "prefix": "in/"})
    src = MinioSource(cfg, client=client)
    assert isinstance(src, S3Source)
    assert (await src.check()).ok
    catalog = await src.discover()
    rows = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data["id"] for r in rows if isinstance(r, Record)] == [1, 2]


def test_minio_catalog_entries_and_secrets() -> None:
    assert MinioSource.definition.name == "minio"
    assert MinioSource.definition.kind is ConnectorKind.SOURCE
    assert MinioDestination.definition.kind is ConnectorKind.DESTINATION
    assert MinioSource.definition.category is ConnectorCategory.STORAGE
    assert MinioSource.secret_fields() == {"access_key", "secret_key"}
    assert MinioDestination.secret_fields() == {"access_key", "secret_key"}
    schema = MinioSource.spec().connection_specification
    assert set(schema["required"]) == {"endpoint", "access_key", "secret_key", "bucket"}
    assert "aws_access_key_id" not in schema["properties"]  # MinIO form has no AWS fields
    assert MinioSource.icon_svg() and MinioDestination.icon_svg()
    with pytest.raises(ConfigValidationError):
        MinioSource.validate_config({"bucket": "b"})


def test_same_name_source_and_destination_coexist_in_registry() -> None:
    reg = ConnectorRegistry()
    for cls in (S3Source, S3Destination, MinioSource, MinioDestination):
        reg.register(cls)
    assert reg.get_source("minio") is MinioSource
    assert reg.get_destination("minio") is MinioDestination
    assert reg.get_source("s3") is S3Source and reg.get_destination("s3") is S3Destination
    assert len(reg) == 4


# ---------------------------------------------------------------------------
# destinations
# ---------------------------------------------------------------------------


def _batch(stream: str, index: int, rows: list[dict[str, Any]], *, last: bool = False) -> Batch:
    return Batch(
        stream=stream,
        records=[Record(stream=stream, data=r) for r in rows],
        batch_index=index,
        is_last=last,
    )


async def _catalog(mode: DestinationSyncMode, streams: list[str]) -> ConfiguredCatalog:
    src = FakeSource.from_config({"rows": 1, "streams": streams})
    return ConfiguredCatalog.from_catalog(await src.discover(), destination_sync_mode=mode)


async def test_destination_writes_jsonl_parts_and_manifest() -> None:
    client = FakeS3()
    dest = MinioDestination(
        MinioDestination.validate_config({**MINIO, "prefix": "lake"}), client=client
    )
    assert (await dest.check()).ok
    catalog = await _catalog(DestinationSyncMode.APPEND, ["orders"])
    await dest.begin(catalog, "conn-1")
    r0 = await dest.write(_batch("orders", 0, [{"id": 1}, {"id": 2}]))
    r1 = await dest.write(_batch("orders", 1, [{"id": 3}]))
    empty = await dest.write(_batch("orders", 2, [], last=True))
    await dest.finalize(catalog, "conn-1")

    assert (r0.records_written, r1.records_written, empty.records_written) == (2, 1, 0)
    keys = sorted(client.objects)
    run = keys[0].split("/")[2]
    assert keys == [
        f"lake/orders/{run}/_manifest.json",
        f"lake/orders/{run}/part-00000.jsonl",
        f"lake/orders/{run}/part-00001.jsonl",
    ]  # the empty closing batch produced no object
    rows = [json.loads(line) for line in client.objects[keys[1]].decode().splitlines()]
    assert [r["id"] for r in rows] == [1, 2]
    assert rows[0]["_stream"] == "orders" and "_emitted_at" in rows[0]
    assert client.content_types[keys[1]] == "application/x-ndjson"
    manifest = json.loads(client.objects[keys[0]])
    assert manifest["records"] == 3 and manifest["objects"] == 2
    assert manifest["connection_id"] == "conn-1" and manifest["destination_sync_mode"] == "append"


async def test_gzip_without_metadata_and_retry_is_idempotent() -> None:
    client = FakeS3()
    cfg = S3Destination.validate_config(
        {"bucket": "b", "compression": "gzip", "include_metadata": False, "write_manifest": False}
    )
    dest = S3Destination(cfg, client=client)
    catalog = await _catalog(DestinationSyncMode.APPEND, ["s"])
    await dest.begin(catalog)
    await dest.write(_batch("s", 0, [{"a": "ü"}]))
    await dest.write(_batch("s", 0, [{"a": "ü"}]))  # retried batch -> same key
    await dest.finalize(catalog)
    assert len(client.objects) == 1
    key = next(iter(client.objects))
    assert key.endswith("part-00000.jsonl.gz") and key.startswith("s/")
    assert json.loads(gzip.decompress(client.objects[key]).decode()) == {"a": "ü"}
    assert client.content_types[key] == "application/gzip"


async def test_manifest_counts_a_retried_batch_once() -> None:
    client = FakeS3()
    dest = S3Destination(S3Destination.validate_config({"bucket": "b"}), client=client)
    catalog = await _catalog(DestinationSyncMode.APPEND, ["s"])
    await dest.begin(catalog)
    await dest.write(_batch("s", 0, [{"a": 1}, {"a": 2}]))
    await dest.write(_batch("s", 0, [{"a": 1}, {"a": 2}]))  # the runner retried the write
    await dest.write(_batch("s", 1, [{"a": 3}]))
    await dest.finalize(catalog)
    manifest = json.loads(client.objects[f"s/{dest._run_id}/_manifest.json"])
    assert (manifest["records"], manifest["objects"]) == (3, 2)  # one object per batch index


async def test_overwrite_retires_older_runs_once_the_new_run_is_complete() -> None:
    old = {
        "lake/orders/old/part-00000.jsonl": b"{}\n",
        "lake/orders/old/_manifest.json": b"{}",
        "lake/orders/older/part-00000.jsonl": b"{}\n",
        "lake/customers/old/part-00000.jsonl": b"{}\n",
    }
    client = FakeS3(dict(old))
    dest = S3Destination(
        S3Destination.validate_config({"bucket": "b", "prefix": "lake/"}), client=client
    )
    catalog = await _catalog(DestinationSyncMode.OVERWRITE, ["orders"])
    await dest.begin(catalog)
    await dest.write(_batch("orders", 0, [{"id": 1}]))
    # The previous run stays readable until this one has landed in full.
    assert set(old) <= set(client.objects) and client.delete_calls == []

    await dest.finalize(catalog)
    run = dest._run_id
    assert sorted(client.objects) == [
        "lake/customers/old/part-00000.jsonl",
        f"lake/orders/{run}/_manifest.json",
        f"lake/orders/{run}/part-00000.jsonl",
    ]
    assert sum(len(c) for c in client.delete_calls) == 3

    append = S3Destination(
        S3Destination.validate_config({"bucket": "b", "prefix": "lake"}), client=client
    )
    append_catalog = await _catalog(DestinationSyncMode.APPEND, ["customers"])
    await append.begin(append_catalog)
    await append.finalize(append_catalog)
    assert "lake/customers/old/part-00000.jsonl" in client.objects


async def test_overwrite_sweeps_older_runs_without_a_manifest_too() -> None:
    client = FakeS3({"orders/old/part-00000.jsonl": b"{}\n"})
    dest = S3Destination(
        S3Destination.validate_config({"bucket": "b", "write_manifest": False}), client=client
    )
    catalog = await _catalog(DestinationSyncMode.OVERWRITE, ["orders"])
    await dest.begin(catalog)
    await dest.write(_batch("orders", 0, [{"id": 1}]))
    await dest.finalize(catalog)
    assert sorted(client.objects) == [f"orders/{dest._run_id}/part-00000.jsonl"]


async def test_s3_connectors_close_the_client_they_built(monkeypatch: pytest.MonkeyPatch) -> None:
    # boto3 clients hold a connection pool; a source or destination that built one releases
    # it when the run ends. A client handed in by the caller is the caller's to close.
    from connector.destinations import s3 as dest_module
    from connector.sources import s3 as src_module

    class _Closable(FakeS3):
        def __init__(self) -> None:
            super().__init__()
            self.closed = False

        def close(self) -> None:
            self.closed = True

    built: list[_Closable] = []

    def build(*args: Any, **kwargs: Any) -> _Closable:
        built.append(_Closable())
        return built[-1]

    monkeypatch.setattr(src_module, "build_s3_client", build)
    monkeypatch.setattr(dest_module, "build_s3_client", build)
    cfg = {"bucket": "b", "region": "eu-west-1"}
    async with S3Source(S3Source.validate_config(cfg)) as src:
        assert (await src.check()).ok
    async with S3Destination(S3Destination.validate_config(cfg)) as dest:
        assert (await dest.check()).ok
    assert len(built) == 2 and all(c.closed for c in built)

    injected = _Closable()
    async with S3Source(S3Source.validate_config(cfg), client=injected):
        pass
    assert not injected.closed


async def test_check_reports_missing_bucket() -> None:
    dest = S3Destination(
        S3Destination.validate_config({"bucket": "nope"}), client=FakeS3(bucket_ok=False)
    )
    result = await dest.check()
    assert not result.ok and "NoSuchBucket" in (result.message or "")


async def test_end_to_end_runner_into_minio(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeS3()
    monkeypatch.setattr("connector.destinations.s3.build_s3_client", lambda *a, **k: client)
    reg = ConnectorRegistry()
    reg.register(FakeSource)
    reg.register(MinioDestination)
    src = FakeSource.from_config({"rows": 5})
    conn = Connection(
        name="e2e",
        source_name="fake",
        source_config={"rows": 5},
        destination_name="minio",
        destination_config={**MINIO, "prefix": "raw"},
        catalog=ConfiguredCatalog.from_catalog(await src.discover()),
    )
    job = await SyncRunner(reg, options=SyncOptions(batch_size=2)).run(conn)
    assert job.status is JobStatus.SUCCEEDED, job.error
    assert job.records_written == 5
    parts = sorted(k for k in client.objects if "part-" in k)
    assert [p.rsplit("/", 1)[1] for p in parts] == [
        "part-00000.jsonl",
        "part-00001.jsonl",
        "part-00002.jsonl",
    ]
    ids = [
        json.loads(line)["id"] for p in parts for line in client.objects[p].decode().splitlines()
    ]
    assert ids == [1, 2, 3, 4, 5]
    manifest = json.loads(
        next(v for k, v in client.objects.items() if k.endswith("_manifest.json"))
    )
    assert manifest["records"] == 5 and manifest["objects"] == 3
