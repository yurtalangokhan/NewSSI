"""DatasourceService over in-process connectors and per-user stored configurations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
import uuid

from connector import (
    BaseSource,
    Catalog,
    CheckResult,
    ConnectorDefinition,
    ConnectorKind,
    Job,
    JobStatus,
    Stream,
    StreamStats,
    SyncMode,
    secret_field,
)
from pydantic import BaseModel
import pytest

from core.exceptions import ApplicationError, BadRequestError, ConflictError, NotFoundError
from service.datasources import datasource_service as module
from service.datasources.datasource_service import DatasourceService, get_datasource_service
from service.ingest import connector_catalog_service as catalog
from service.ingest.connector_runtime import ConnectorConfigMissingError, build_registry

OWNER = "0b0e7a4e-1d7c-4f0e-9d3c-5a4f6f3b2a10"


class _DemoConfig(BaseModel):
    host: str
    password: str = secret_field(default="")


class _DemoSource(BaseSource[_DemoConfig]):
    definition = ConnectorDefinition(name="demo", display_name="Demo DB", kind=ConnectorKind.SOURCE)
    Config = _DemoConfig

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        if self.config.host == "unreachable":
            raise ConnectionError("no route to host")
        modes = [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]
        return Catalog(
            streams=[
                Stream(name="orders", supported_sync_modes=modes, json_schema={"properties": {"id": {}, "total": {}}}),
                Stream(name="customers", supported_sync_modes=modes, source_defined_primary_key=[["id"]]),
            ]
        )

    def read(self, catalog: Any, state: Any = None):  # pragma: no cover - syncs are faked
        raise NotImplementedError


class FakeDatasourceRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.fail_create = False

    def _row(self, row):
        return {"uuid": row["uuid"], "name": row["name"], "cmetadata": dict(row["cmetadata"])} if row else None

    async def list_datasource_collections(self):
        return [{**self._row(r), "doc_count": 0} for r in self.rows.values() if r["cmetadata"].get("connector_type")]

    async def get_collection(self, collection_id):
        return self._row(self.rows.get(collection_id))

    async def get_collection_by_name(self, name):
        return self._row(next((r for r in self.rows.values() if r["name"] == name), None))

    async def create_collection(self, collection_uuid, name, cmetadata=None):
        if self.fail_create:
            raise RuntimeError("database is down")
        self.rows[collection_uuid] = {"uuid": collection_uuid, "name": name, "cmetadata": dict(cmetadata or {})}
        return self._row(self.rows[collection_uuid])

    async def update_collection_metadata(self, collection_id, cmetadata):
        self.rows[collection_id]["cmetadata"] = dict(cmetadata)
        return self._row(self.rows[collection_id])

    async def update_collection(self, collection_id, *, name=None, cmetadata=None):
        if name is not None:
            self.rows[collection_id]["name"] = name
        if cmetadata is not None:
            self.rows[collection_id]["cmetadata"] = dict(cmetadata)
        return self._row(self.rows[collection_id])

    async def delete_collection(self, collection_id):
        return self.rows.pop(collection_id, None) is not None

    async def count_embeddings(self, collection_id):
        return 0

    async def get_paginated_embeddings(self, collection_id, *, limit=10, offset=0):
        return [{"document": "x" * 600, "cmetadata": {"stream": "orders"}}]


class FakeConnectionRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def get(self, datasource_id):
        row = self.rows.get(datasource_id)
        return dict(row) if row else None

    async def list_all(self):
        return [dict(r) for r in self.rows.values()]

    async def create(self, datasource_id, connector_name, config_id, owner_user_id, catalog, *, update_graph_rag=False):
        self.rows[datasource_id] = {
            "datasource_id": datasource_id,
            "connector_name": connector_name,
            "config_id": config_id,
            "owner_user_id": owner_user_id,
            "catalog": catalog,
            "update_graph_rag": update_graph_rag,
        }
        return dict(self.rows[datasource_id])

    async def update(self, datasource_id, **fields):
        self.rows[datasource_id].update(fields)
        return dict(self.rows[datasource_id])

    async def delete(self, datasource_id):
        return self.rows.pop(datasource_id, None) is not None


class FakeScheduleRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def get_by_datasource(self, datasource_id):
        return self.rows.get(datasource_id)

    async def list_all(self):
        return list(self.rows.values())

    @staticmethod
    def next_run_iso(cron_expr, tz_name="UTC"):
        return "2030-01-01T00:00:00+00:00"


class FakeConfigs:
    """The user-service connector-configuration client."""

    def __init__(self) -> None:
        self.stored: dict[str, dict[str, Any]] = {}

    async def create_connector_config(self, owner_id, connector_name, name, config):
        config_id = str(uuid.uuid4())
        self.stored[config_id] = {"owner": owner_id, "connector_name": connector_name, "name": name, "config": config}
        return {"id": config_id}

    async def get_connector_config(self, owner_id, config_id):
        row = self.stored.get(config_id)
        return {"id": config_id, "config": row["config"]} if row and row["owner"] == owner_id else None

    async def update_connector_config(self, owner_id, config_id, *, name=None, config=None):
        row = self.stored.get(config_id)
        if row is None:  # what the client raises for user-service's 404
            raise ApplicationError(status_code=404, code="user_service.error", message="User service returned an error.")
        if name is not None:
            row["name"] = name
        if config is not None:
            row["config"] = config
        return {"id": config_id}

    async def delete_connector_config(self, owner_id, config_id):
        self.stored.pop(config_id, None)


class FakeRuntime:
    def __init__(self, registry) -> None:
        self.registry = registry
        self.started: list[str] = []
        self.start_calls: list[dict[str, Any]] = []
        self.history: list[Job] = []
        self.start_result: Any = "job"
        self.cancelled: list[str] = []
        self.reset_calls: list[str] = []
        self.jobs = SimpleNamespace(list=self._list)
        self.runner = SimpleNamespace(active_job_id=lambda ds: "job-1" if ds in self.started else None, cancel=self._cancel)

    async def _list(self, datasource_id, limit=50):
        return [job for job in self.history if job.connection_id == datasource_id][:limit]

    async def _cancel(self, job_id):
        self.cancelled.append(job_id)
        return True

    async def start_sync(self, datasource_id, **kwargs):
        self.start_calls.append(kwargs)
        if isinstance(self.start_result, Exception):
            raise self.start_result
        if self.start_result is None:
            return None
        self.started.append(datasource_id)
        return Job(id="job-1", connection_id=datasource_id)

    async def queue_position(self, datasource_id):
        return None

    async def is_active(self, datasource_id):
        return datasource_id in self.started

    async def latest_job(self, datasource_id):
        jobs = await self._list(datasource_id)
        return jobs[0] if jobs else None

    async def reset_checkpoints(self, datasource_id):
        self.reset_calls.append(datasource_id)


@pytest.fixture
def env(monkeypatch):
    registry = build_registry()
    registry.register(_DemoSource)
    runtime = FakeRuntime(registry)
    monkeypatch.setattr(catalog, "get_connector_runtime", lambda: runtime)

    async def graph_unavailable():
        return False

    async def no_assistant(assistant_id):
        return None

    monkeypatch.setattr(module, "is_graph_rag_available", graph_unavailable)
    monkeypatch.setattr(module, "get_assistant_from_store", no_assistant)
    parts = SimpleNamespace(
        ds=FakeDatasourceRepo(),
        connections=FakeConnectionRepo(),
        schedules=FakeScheduleRepo(),
        configs=FakeConfigs(),
        runtime=runtime,
        monkeypatch=monkeypatch,
        rag_deletes=[],
    )

    async def rag_delete(collection_id):
        # rag-service resolves the Milvus table from the collection row: it must still be there.
        assert collection_id in parts.ds.rows
        parts.rag_deletes.append(collection_id)
        return {"chunks_removed": 5}

    monkeypatch.setattr(module.rag_client, "delete_datasource_records", rag_delete)
    parts.service = DatasourceService(
        ds_repo=parts.ds,
        connection_repo=parts.connections,
        schedule_repo=parts.schedules,
        configs=parts.configs,
        runtime=runtime,
    )
    return parts


async def _create(env, name="Sales", streams=None):
    return await env.service.create_datasource(
        name, "demo", {"host": "db", "password": "s3cret"}, streams=streams, owner_user_id=OWNER
    )


@pytest.mark.asyncio
async def test_create_stores_the_config_for_the_owner_and_links_it(env):
    created = await _create(env, streams=["orders"])

    assert created["connector_type"] == "demo" and created["connector_display_name"] == "Demo DB"
    [(config_id, stored)] = env.configs.stored.items()
    assert stored["owner"] == OWNER and stored["config"] == {"host": "db", "password": "s3cret"}

    connection = env.connections.rows[created["id"]]
    assert connection["config_id"] == config_id and connection["owner_user_id"] == OWNER
    assert [s["stream"]["name"] for s in connection["catalog"]["streams"]] == ["orders"]
    meta = env.ds.rows[created["id"]]["cmetadata"]
    assert meta["connector_type"] == "demo" and meta["streams"] == ["orders"]
    assert "password" not in str(meta), "credentials never reach the collection metadata"


@pytest.mark.asyncio
async def test_create_rejects_duplicates_unknown_connectors_and_bad_configs(env):
    await _create(env)

    with pytest.raises(ConflictError):
        await _create(env)
    with pytest.raises(BadRequestError, match="Unknown connector"):
        await env.service.create_datasource("Other", "nope", {}, owner_user_id=OWNER)
    with pytest.raises(BadRequestError, match="host"):
        await env.service.create_datasource("Other", "demo", {"password": "x"}, owner_user_id=OWNER)
    with pytest.raises(BadRequestError, match="no route to host"):
        await env.service.create_datasource("Other", "demo", {"host": "unreachable"}, owner_user_id=OWNER)

    assert len(env.configs.stored) == 1 and len(env.ds.rows) == 1


@pytest.mark.asyncio
async def test_discovery_errors_carry_no_credential(env):
    # Discovery runs for datasource:update holders and source previews, who only ever see
    # masked secrets; a driver that quotes its address (key in the query, password in the
    # DSN) or echoes the configured secret must not undo that through the error message.
    async def leaky_discover(self):
        raise ConnectionError(
            f"401 for url 'https://{self.config.host}/items?api_key={self.config.password}' "
            f"(sent password {self.config.password})"
        )

    env.monkeypatch.setattr(_DemoSource, "discover", leaky_discover)
    with pytest.raises(BadRequestError) as refused:
        await env.service.create_datasource(
            "Other", "demo", {"host": "api.example.com", "password": "pw-SECRET-1"}, owner_user_id=OWNER
        )
    message = str(refused.value)
    assert "pw-SECRET-1" not in message and "?api_key=" not in message
    assert "https://api.example.com/items?***" in message and "sent password ***" in message


@pytest.mark.asyncio
async def test_create_removes_the_stored_config_when_the_collection_cannot_be_created(env):
    env.ds.fail_create = True

    with pytest.raises(Exception):  # noqa: B017 - rendered as the contract's generic 500
        await _create(env)

    assert env.configs.stored == {} and env.connections.rows == {}


@pytest.mark.asyncio
async def test_a_principal_without_a_user_id_owns_its_configs_under_a_stable_uuid(env):
    await env.service.create_datasource("Dev", "demo", {"host": "db"}, owner_user_id="dev-user")
    await env.service.create_datasource("Dev 2", "demo", {"host": "db"}, owner_user_id="dev-user")

    owners = {row["owner"] for row in env.configs.stored.values()}
    assert len(owners) == 1 and str(uuid.UUID(next(iter(owners)))) == next(iter(owners))


@pytest.mark.asyncio
async def test_details_mask_the_config_and_report_modes_and_schedule(env):
    created = await _create(env)
    env.schedules.rows[created["id"]] = {
        "datasource_id": created["id"],
        "cron_expression": "0 0 3 * * ?",
        "enabled": True,
        "timezone": "UTC",
        "next_run_at": "2030-01-02T03:00:00+00:00",
    }
    finished = datetime(2026, 9, 1, 3, 0, 9, tzinfo=UTC)
    env.runtime.history.append(Job(connection_id=created["id"], status=JobStatus.SUCCEEDED, finished_at=finished))

    details = await env.service.get_datasource_details(created["id"])

    assert details["config"] == {"host": "db", "password": catalog.SECRET_MASK}
    assert details["sync_mode"] == "full_refresh" and details["destination_sync_mode"] == "overwrite"
    assert details["schedule"]["cron_expression"] == "0 0 3 * * ?"
    assert details["schedule"]["last_run_status"] == "succeeded"
    assert details["schedule"]["last_run_at"] == "2026-09-01T03:00:09Z"
    assert details["chunks"][0]["content"].endswith("...") and details["chunks"][0]["stream"] == "orders"
    assert details["graph_rag_available"] is False

    with pytest.raises(NotFoundError):
        await env.service.get_datasource_details(str(uuid.uuid4()))

    # A caller who may not edit the connection gets no connection settings, and the
    # stored configuration is not even read for them.
    async def no_config_read(owner_id, config_id):
        raise AssertionError("the stored configuration must not be fetched")

    env.configs.get_connector_config = no_config_read
    limited = await env.service.get_datasource_details(created["id"], include_config=False)
    assert limited["config"] == {}
    assert limited["chunks"] == details["chunks"]
    assert limited["schedule"]["cron_expression"] == details["schedule"]["cron_expression"]


@pytest.mark.asyncio
async def test_update_keeps_a_masked_secret_and_changes_streams_and_modes(env):
    created = await _create(env)
    [config_id] = env.configs.stored

    await env.service.update_datasource(
        created["id"],
        name="Sales EU",
        connector_config={"host": "db-eu", "password": catalog.SECRET_MASK},
        streams=["customers"],
        sync_mode="incremental",
        destination_sync_mode="append",
    )

    assert env.configs.stored[config_id]["config"] == {"host": "db-eu", "password": "s3cret"}
    assert env.configs.stored[config_id]["name"] == "Sales EU"
    [stream] = env.connections.rows[created["id"]]["catalog"]["streams"]
    assert stream["stream"]["name"] == "customers"
    assert stream["sync_mode"] == "incremental" and stream["destination_sync_mode"] == "append"
    row = env.ds.rows[created["id"]]
    assert row["name"] == "Sales EU" and row["cmetadata"]["streams"] == ["customers"]

    with pytest.raises(BadRequestError, match="Invalid sync mode"):
        await env.service.update_datasource(created["id"], sync_mode="incremental", destination_sync_mode="overwrite")


@pytest.mark.asyncio
async def test_a_datasource_without_a_connection_gets_one_when_a_config_is_saved(env):
    legacy_id = str(uuid.uuid4())
    env.ds.rows[legacy_id] = {
        "uuid": legacy_id,
        "name": "Legacy",
        "cmetadata": {"connector_type": "source-demo", "connector_config": {"password": "old"}},
    }

    with pytest.raises(BadRequestError):
        await env.service.trigger_sync(legacy_id)
    with pytest.raises(BadRequestError):
        await env.service.update_datasource(legacy_id, name="Still legacy")

    await env.service.update_datasource(legacy_id, connector_config={"host": "db"}, acting_user_id=OWNER)

    connection = env.connections.rows[legacy_id]
    assert connection["connector_name"] == "demo" and connection["owner_user_id"] == OWNER
    meta = env.ds.rows[legacy_id]["cmetadata"]
    assert meta["connector_type"] == "demo" and "connector_config" not in meta


@pytest.mark.asyncio
async def test_delete_removes_the_stored_config_the_connection_and_the_collection(env):
    created = await _create(env)
    env.runtime.started.append(created["id"])

    assert await env.service.delete_datasource(created["id"]) == {"status": "deleted", "id": created["id"]}

    assert env.configs.stored == {} and env.connections.rows == {} and env.ds.rows == {}
    assert env.runtime.cancelled == ["job-1"]
    assert env.rag_deletes == [created["id"]]


@pytest.mark.asyncio
async def test_delete_goes_on_when_rag_service_holds_nothing_for_the_datasource(env):
    created = await _create(env)

    async def unknown_collection(collection_id):
        raise ApplicationError(status_code=404, code="collection.not_found", message="gone", message_key=None)

    env.monkeypatch.setattr(module.rag_client, "delete_datasource_records", unknown_collection)

    assert await env.service.delete_datasource(created["id"]) == {"status": "deleted", "id": created["id"]}
    assert env.configs.stored == {} and env.connections.rows == {} and env.ds.rows == {}


@pytest.mark.asyncio
async def test_delete_keeps_the_datasource_when_rag_service_cannot_drop_its_chunks(env):
    created = await _create(env)

    async def rag_down(collection_id):
        raise ApplicationError(status_code=503, code="dependency.unavailable", message="down", message_key=None)

    env.monkeypatch.setattr(module.rag_client, "delete_datasource_records", rag_down)

    with pytest.raises(ApplicationError) as raised:
        await env.service.delete_datasource(created["id"])

    assert raised.value.status_code == 503
    assert created["id"] in env.ds.rows and created["id"] in env.connections.rows
    assert env.configs.stored != {}


@pytest.mark.asyncio
async def test_trigger_sync_passes_full_refresh_to_the_runtime(env):
    created = await _create(env)

    await env.service.trigger_sync(created["id"])
    await env.service.trigger_sync(created["id"], full_refresh=True)

    assert [call["full_refresh"] for call in env.runtime.start_calls] == [False, True]


@pytest.mark.asyncio
async def test_trigger_sync_reports_started_queued_and_failures(env):
    created = await _create(env)

    assert await env.service.trigger_sync(created["id"]) == {"status": "Sync started", "id": created["id"]}

    # A trigger that starts nothing changes nothing: the running sync keeps its progress.
    env.ds.rows[created["id"]]["cmetadata"].update(sync_status="syncing", sync_progress=10)
    env.runtime.start_result = None
    assert (await env.service.trigger_sync(created["id"]))["status"] == "Already syncing or queued"
    meta = env.ds.rows[created["id"]]["cmetadata"]
    assert meta["sync_status"] == "syncing" and meta["sync_progress"] == 10

    env.runtime.start_result = ConnectorConfigMissingError()
    with pytest.raises(BadRequestError):
        await env.service.trigger_sync(created["id"])
    meta = env.ds.rows[created["id"]]["cmetadata"]
    assert meta["sync_status"] == "error" and "missing" in meta["last_error"]

    # Anything else is not "the configuration is missing": it surfaces as it is.
    env.runtime.start_result = RuntimeError("job store unreachable")
    with pytest.raises(RuntimeError, match="job store unreachable"):
        await env.service.trigger_sync(created["id"])
    assert env.ds.rows[created["id"]]["cmetadata"]["last_error"] == "job store unreachable"

    # What is kept for every reader of the datasource carries no credential.
    env.runtime.start_result = RuntimeError("503 for url 'http://user-service/configs/1?token=tok-SECRET'")
    with pytest.raises(RuntimeError):
        await env.service.trigger_sync(created["id"])
    assert env.ds.rows[created["id"]]["cmetadata"]["last_error"] == "503 for url 'http://user-service/configs/1?***'"


@pytest.mark.asyncio
async def test_saving_the_config_again_replaces_a_stored_config_that_is_gone(env):
    created = await _create(env)
    [lost_id] = env.configs.stored
    del env.configs.stored[lost_id]  # the row user-service kept for the owner is gone

    # The mask stands for a stored secret, and there is none left to put back.
    with pytest.raises(BadRequestError, match="password"):
        await env.service.update_datasource(
            created["id"], connector_config={"host": "db", "password": catalog.SECRET_MASK}
        )
    assert env.configs.stored == {}

    await env.service.update_datasource(created["id"], connector_config={"host": "db-2", "password": "n3w"})

    [(config_id, stored)] = env.configs.stored.items()
    assert config_id != lost_id and stored["owner"] == OWNER
    assert stored["config"] == {"host": "db-2", "password": "n3w"} and stored["connector_name"] == "demo"
    connection = env.connections.rows[created["id"]]
    assert connection["config_id"] == config_id and connection["owner_user_id"] == OWNER
    assert (await env.service.get_datasource_details(created["id"]))["config"]["host"] == "db-2"


@pytest.mark.asyncio
async def test_status_history_list_and_preview(env):
    created = await _create(env)
    started = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
    env.runtime.history.append(
        Job(
            id="job-9",
            connection_id=created["id"],
            status=JobStatus.FAILED,
            created_at=started,
            started_at=started,
            finished_at=started + timedelta(seconds=42),
            stats={"orders": StreamStats(records_read=5, records_written=4, batches=1)},
            error="boom",
        )
    )

    [entry] = await env.service.get_sync_history(created["id"])
    assert entry == {
        "id": "job-9",
        "status": "failed",
        "created_at": int(started.timestamp()),
        "updated_at": int(started.timestamp()) + 42,
        "duration_seconds": 42,
        "bytes_synced": 0,
        "records_synced": 5,
        "error_message": "boom",
    }

    status = await env.service.get_sync_status(created["id"])
    assert status["sync_status"] == "idle" and status["is_active"] is False and status["schedule"] is None

    [listed] = await env.service.list_datasources()
    assert listed["id"] == created["id"] and listed["connector_display_name"] == "Demo DB"
    assert listed["schedule_summary"] is None

    preview = await env.service.source_preview(created["id"])
    assert [s["name"] for s in preview["streams"]] == ["orders", "customers"]
    assert preview["streams"][0]["field_count"] == 2 and preview["connector_type"] == "demo"


@pytest.mark.asyncio
async def test_the_reason_of_a_failed_sync_is_for_callers_who_may_run_syncs(env):
    created = await _create(env)
    reason = "OperationalError: connection to db-7.internal as etl_user refused"
    env.ds.rows[created["id"]]["cmetadata"].update(sync_status="error", last_error=reason)
    env.runtime.history += [
        Job(id="job-2", connection_id=created["id"], status=JobStatus.FAILED, error=reason),
        Job(id="job-1", connection_id=created["id"], status=JobStatus.SUCCEEDED),
    ]

    details = await env.service.get_datasource_details(created["id"])
    status = await env.service.get_sync_status(created["id"])
    failed, succeeded = await env.service.get_sync_history(created["id"])
    assert details["last_error"] == status["last_error"] == failed["error_message"] == reason

    hidden = "The sync did not complete. The reason is shown to users who can run syncs."
    details = await env.service.get_datasource_details(created["id"], include_error_detail=False)
    status = await env.service.get_sync_status(created["id"], include_error_detail=False)
    failed, succeeded = await env.service.get_sync_history(created["id"], include_error_detail=False)
    assert details["last_error"] == status["last_error"] == failed["error_message"] == hidden
    # That a sync failed is no secret, and a sync that did not fail gets no error.
    assert status["sync_status"] == "error" and failed["status"] == "failed"
    assert succeeded["error_message"] is None

    updated = await env.service.update_datasource(created["id"], name="Sales EU", include_error_detail=False)
    assert updated["last_error"] == hidden

    del env.ds.rows[created["id"]]["cmetadata"]["last_error"]
    assert (await env.service.get_sync_status(created["id"], include_error_detail=False))["last_error"] is None


def test_get_datasource_service_factory():
    assert isinstance(get_datasource_service(), DatasourceService)

@pytest.mark.asyncio
async def test_a_changed_config_forgets_the_saved_checkpoints(env):
    # A connection pointed elsewhere must not skip the rows its old cursor says it
    # has seen; a rotated credential re-reads as well, which is the safe side.
    created = await _create(env)

    await env.service.update_datasource(created["id"], connector_config={"host": "db-2", "password": "n3w"})

    assert env.runtime.reset_calls == [created["id"]]


@pytest.mark.asyncio
async def test_saving_the_same_config_again_keeps_the_checkpoints(env):
    created = await _create(env)

    await env.service.update_datasource(
        created["id"], connector_config={"host": "db", "password": catalog.SECRET_MASK}
    )

    assert env.runtime.reset_calls == []


@pytest.mark.asyncio
async def test_a_name_stream_or_mode_change_keeps_the_checkpoints(env):
    created = await _create(env)

    await env.service.update_datasource(created["id"], name="Renamed", streams=["customers"])
    await env.service.update_datasource(created["id"], sync_mode="incremental", destination_sync_mode="append")

    assert env.runtime.reset_calls == []
