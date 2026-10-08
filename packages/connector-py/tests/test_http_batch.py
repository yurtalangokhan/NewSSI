from __future__ import annotations

import httpx
import pytest

from connector import (
    Batch,
    ConfiguredCatalog,
    Connection,
    ConnectorRegistry,
    JobStatus,
    Record,
    RegistryConnectorFactory,
    SyncOptions,
    SyncRunner,
)
from connector.destinations.http_batch import HttpBatchDestination
from tests.conftest import FakeSource


def _dest(handler, **cfg) -> HttpBatchDestination:  # noqa: ANN001, ANN003
    config = HttpBatchDestination.validate_config(
        {"base_url": "http://svc", "batch_path": "/ingest/batch", "datasource_id": "ds-1", **cfg}
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://svc")
    return HttpBatchDestination(config, client=client)


def test_payload_matches_ingest_contract() -> None:
    dest = _dest(lambda r: httpx.Response(200), connector_type="postgres")
    batch = Batch(
        stream="orders",
        records=[Record(stream="orders", data={"id": 1})],
        batch_index=2,
        is_last=True,
        job_id="job-9",
    )
    payload = dest.build_payload(batch)
    assert payload == {
        "datasource_id": "ds-1",
        "connector_type": "postgres",
        "stream_name": "orders",
        "batch_id": "ds-1:job-9:orders:2",  # (job_id, stream, batch_index) survives retries
        "records": [{"id": 1, "_stream": "orders"}],
        "batch_index": 2,
        "is_last_batch": True,
    }
    # Written outside a sync run there is no job to name.
    outside_a_run = Batch(stream="orders", records=[], batch_index=0)
    assert dest.build_payload(outside_a_run)["batch_id"] == "ds-1:orders:0"


def test_the_receiving_path_has_no_default() -> None:
    # Nothing in the platform serves ``/ingest/batch``; the operator names the endpoint.
    from connector import ConfigValidationError

    with pytest.raises(ConfigValidationError):
        HttpBatchDestination.validate_config({"base_url": "http://svc", "datasource_id": "ds-1"})


async def test_write_posts_and_reads_chunks_indexed() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/health":
            return httpx.Response(200)
        return httpx.Response(200, json={"status": "ok", "chunks_indexed": 7})

    dest = _dest(handler, bearer_token="secret")
    dest._get_client().headers["Authorization"] = (
        "Bearer secret"  # injected client mimics owned client
    )
    assert (await dest.check()).ok
    result = await dest.write(
        Batch(stream="s", records=[Record(stream="s", data={"a": 1})], batch_index=0)
    )
    assert result.records_written == 1 and result.extra["chunks_indexed"] == 7
    assert calls[-1].url.path == "/ingest/batch"
    assert calls[-1].headers["authorization"] == "Bearer secret"


async def test_write_raises_on_http_error() -> None:
    dest = _dest(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        await dest.write(Batch(stream="s", records=[], batch_index=0))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
async def test_rejected_batches_are_not_retried(status: int) -> None:
    # The receiver said no to this payload; sending it again three times cannot help.
    from connector import DestinationWriteError

    dest = _dest(lambda r: httpx.Response(status, text="bad payload"))
    with pytest.raises(DestinationWriteError, match=f"{status}.*bad payload"):
        await dest.write(Batch(stream="s", records=[], batch_index=0))


@pytest.mark.parametrize("status", [408, 429])
async def test_timeouts_and_rate_limits_stay_retryable(status: int) -> None:
    dest = _dest(lambda r: httpx.Response(status, text="later"))
    with pytest.raises(httpx.HTTPStatusError):
        await dest.write(Batch(stream="s", records=[], batch_index=0))


async def test_check_reports_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    dest = _dest(handler)
    result = await dest.check()
    assert not result.ok and "refused" in (result.message or "")


async def test_end_to_end_with_runner() -> None:
    """Runner -> HttpBatchDestination -> mocked receiver, the client handed in by a factory."""
    received: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        received.append(json.loads(request.content))
        return httpx.Response(200, json={"chunks_indexed": 1})

    reg = ConnectorRegistry()
    reg.register(FakeSource)
    reg.register(HttpBatchDestination)

    class SharedClientFactory(RegistryConnectorFactory):
        async def destination(self, connection: Connection) -> HttpBatchDestination:
            config = HttpBatchDestination.validate_config(connection.destination_config)
            client = httpx.AsyncClient(
                base_url=config.base_url, transport=httpx.MockTransport(handler)
            )
            return HttpBatchDestination(config, client=client)

    src = FakeSource.from_config({"rows": 5})
    conn = Connection(
        name="e2e",
        source_name="fake",
        source_config={"rows": 5},
        destination_name="http_batch",
        destination_config={
            "base_url": "http://svc",
            "batch_path": "/ingest/batch",
            "datasource_id": "ds",
            "connector_type": "fake",
        },
        catalog=ConfiguredCatalog.from_catalog(await src.discover()),
    )
    job = await SyncRunner(SharedClientFactory(reg), options=SyncOptions(batch_size=2)).run(conn)
    assert job.status is JobStatus.SUCCEEDED, job.error
    # 2 + 2, State checkpoint flushes the last 1, then an empty closing batch.
    assert [p["batch_index"] for p in received] == [0, 1, 2, 3]
    assert [len(p["records"]) for p in received] == [2, 2, 1, 0]
    assert received[-1]["is_last_batch"] is True and received[0]["is_last_batch"] is False
    assert received[0]["records"][0]["_stream"] == "a"
