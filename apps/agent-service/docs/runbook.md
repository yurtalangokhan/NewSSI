# Agent service runbook

Use this runbook for local startup, operational checks, and provider-specific
runtime setup.

## Startup

Run these commands from `apps/agent-service/` unless noted otherwise.

```sh
make dev-install
make run
```

The root stack uses APISIX for external traffic. Direct local service access
uses the port configured in environment files. Do not hardcode service ports in
code or documentation snippets.

On Windows, set `POSTGRES_HOST=127.0.0.1` when Docker publishes Postgres on IPv4
loopback. The async LangGraph Postgres pool can stall on `localhost` when it
resolves to an unavailable IPv6 loopback address first.

## User-service circuit breaker

User-service requests use the shared outbound HTTP wrapper. An open circuit
becomes a dependency-unavailable error with a retry interval. Permission checks
fail closed through the existing authorization policy instead of leaking the
breaker exception as an HTTP 500. Check earlier connection or timeout errors
to identify why the circuit opened, and verify user-service readiness through
APISIX before retrying after the reset interval.

## Development without real model credentials

Set `FAKE_MODEL=true` when you need local tests or smoke checks without calling
a real LLM provider. Production and shared environments must resolve the model
through configured provider defaults.

## Provider notes

- Use [Ollama](ollama.md) for local model setup.
- Use [Google models](google-models.md) for Gemini Developer API and Vertex AI
  setup.
- Use [file-based credentials](file-based-credentials.md) for local credential
  files that must not be committed or baked into images.

## Live connector checks

Assigned connector tools require a running tools-service that advertises
`connector_list_resources` and `connector_read`. Restart tools-service after
adding tool modules, and reload agent-service to clear its tool cache. A configurable
agent refuses to run when an assigned connector tool is missing.

Set tools-service's `AGENT_SERVICE_URL` to the configured agent API base, including
`/api/v1`, and configure matching internal service authentication. The callback
resolves only connectors and operations assigned to the saved agent.

Connector configurations are stored by user-service. The resolver reads the
assigned datasource's configuration through `INTERNAL_USER_SERVICE_URL` with the
internal service token; credentials remain server-side. A missing or unreadable
stored configuration produces a connector error; indexing does not resolve it.
Confirm a successful `connector_read` before treating output as source data.
If a model prints connector-call JSON instead of issuing a native tool call, the
configurable agent retries the model once per user turn. The JSON itself is never
executed. Repeated malformed output produces an explicit failure response.

When tools-service runs outside Docker, a source's Docker hostname may be
unreachable. Set tools-service's optional `CONNECTOR_POSTGRES_ENDPOINTS` to a JSON
object keyed by saved datasource ID, with `host` and integer `port` values for its
published PostgreSQL endpoint. Only that datasource's live-read host and port are
overridden; saved credentials, database, selected streams, and the sync
configuration remain unchanged. This setting is administrator configuration and
is never accepted from model arguments.

## Datasource syncs

Syncs run inside this process through `packages/connector-py`, wired in
`src/service/ingest/connector_runtime.py`: a registry, one `SyncRunner` and one
`SyncScheduler` over the service's own tables. The application lifespan starts
and stops them.

**Configuration is fetched when a job runs.** A connection carries only
`config_id` and `owner_user_id`. `DatasourceConnectorFactory` reads the
configuration from user-service at the moment a job starts running, so
scheduler polls and status lookups never touch credentials. User-service
therefore has to be reachable when a sync starts, not when it is scheduled. A
manual trigger that is going to start a job also reads the configuration once
up front: when it is gone the trigger answers 400 instead of queueing a job
that cannot run. A scheduled run in the same state is recorded as a failed job
whose error says to save the datasource configuration again; doing so
(`PUT /datasources/{id}` with `connector_config`) stores the configuration
anew for the same owner and points the connection at it.

**One live job per datasource.** `connector_sync_jobs` admits a single
`pending` or `running` row per datasource (partial unique index
`uq_connector_sync_jobs_active`, migration `0052`). A second trigger while one
is live starts nothing: it reads no configuration and leaves the datasource's
`sync_status` as the running job reported it (`starting` when the job is
created, `syncing` once it runs). Jobs beyond `CONNECTOR_MAX_CONCURRENT_SYNCS`
wait as `pending` and keep their heartbeat. The Graph RAG rebuild that may
follow a successful sync (`update_graph_rag`) is followed in a task of its own,
not inside the job: the slot is free as soon as the sync is over, while
`graph_update_status` goes from `graph_rebuilding` to `graph_completed`,
`graph_failed`, `graph_timeout` (10 minutes) or `graph_unavailable`. A restart
stops following a build; rag-service goes on with it and its status page shows
the outcome.

**Dead workers.** A running job refreshes `heartbeat_at` every 30 seconds.
After 90 seconds of silence it belongs to a process that is gone: the next
trigger or scheduler poll marks it `failed` ("interrupted: its worker stopped
responding" or "interrupted by service restart"), shows that on the datasource
(`sync_status` `error`), and the scheduler runs the datasource again from its
last checkpoint. A heartbeat or final status the database refuses does not end
the job or hold its slot: a missed beat is logged ("heartbeat of job ... could
not be stored") and the next one is tried, and the final status is written
with retries. Checkpoints are also saved in the
middle of a large ordered stream, so the rerun does not start that stream
over. Do not delete job rows to unblock a datasource; wait for the heartbeat
to go stale. A worker that was only silent, and comes back after its job was
declared dead, ends that run at its next heartbeat or batch: the job stays
`failed` ("superseded: another worker declared this job dead and took over")
and a live status is never written back over the sibling's verdict. At most
the batch in flight when the worker woke up is written twice; record keys
absorb it.

**Stopping a sync.** A sync is stopped when its datasource is deleted, when
`CONNECTOR_SYNC_TIMEOUT_SECONDS` (24 hours by default, `0` for no limit) runs
out, or when the service shuts down; a shutdown leaves the job resumable. The
limit is there to give back the slot of a source that hangs: a job that runs
into it ends `failed` with "timed out after ...s", and its incremental streams
continue from their last checkpoint on the next run. A full refresh that needs
longer than the limit can never finish, so raise the limit for it. The S3 and
Spark sources read through blocking drivers in a worker thread and first let
the driver call that is in flight return, so stopping them can take as long
as that call.

**Writes to rag-service.** Every batch goes to
`POST /datasources/{id}/records` with the idempotency key
`connector-sync.<datasource>.<job>.<stream digest>.<batch index>` (the retire
at the end of an overwrite sync ends in `.retire`; a graph rebuild uses
`graph-build.<datasource>.<job>`). rag-service splits and embeds the batch
inside the request, so the call runs under its own outbound dependency,
`rag-service-ingest` in `configs/resilience.yaml`: a 15-minute budget, no
transport-level retry, and a circuit breaker separate from the one chat
retrieval uses, so a slow or failing ingest never takes retrieval down with it.
A batch whose answer was lost is replayed by rag-service when it is retried. A
batch rag-service failed with `429` or `5xx` is sent again under the same key
and runs again: five attempts per batch, waiting 5, 10, 20 and 40 seconds, so a
rag-service restart and the 30 seconds its breaker then stays open are
outlasted. A batch it refused for another reason is not run again (`409
idempotency_key_reused`), so the job fails at once with the first error as its
reason. Trigger the sync again: the new job has new keys.

**One version per record.** Every record goes to rag-service with a record
key: the primary-key values of its stream (the key the sync was configured
with, else the one the source declares), or the whole record when the stream
has no primary key or the record no value for it. rag-service replaces the
chunks stored under a key when the record is written again, so a retried
batch, a job that runs again from its last checkpoint and an `append` sync
that meets a changed record all leave one version. A record without a primary
key is replaced only when it comes again unchanged; a changed one, and every
changed file of a file source, is stored next to its old version until an
`overwrite` sync. Rows that are identical in every field are one record.

**What a chunk carries.** A record goes to rag-service as its text (the
well-known identifying and text fields, else every field as `key: value`) plus
metadata rag-service copies onto every chunk: `source`, `stream`,
`connector_type`, the job id, and the record's other fields. The text fields
themselves (`content`, `body`, `text`, `message`, `value`) stay out of the
metadata, a value is cut at 4 096 characters (a nested one over that is
dropped), and the whole stays under 32 KiB: Milvus stores it as one JSON field
of at most 64 KiB, and a record over that failed its batch for good.

**Overwrite without an empty window.** An `overwrite` sync (the default) does
not clear the collection first. Every document it sends carries the job id in
`metadata._sync_job_id`; the records land next to the previous version, which
stays searchable the whole time, and when the last batch is in, the
destination's `finalize` calls `POST /datasources/{id}/records/retire` with the
job id: rag-service removes every chunk the run did not write (chunks of
earlier runs, and chunks written before runs were tagged). A run that fails
leaves the previous version in place, next to the records the failed run had
already written; the next successful sync retires both. A catalog that mixes
`overwrite` and `append` streams is never retired (stream names cannot scope
the filter); it is logged and the previous version stays.

**Deleting a datasource.** `DELETE /api/v1/datasources/{id}` cancels a running
sync, then calls rag-service's `DELETE /datasources/{id}/records`, which drops
the collection's Milvus table while the collection row still names it; the
stored configuration, the connection and the collection row (with its schedule,
jobs and checkpoints) go afterwards. A 404 from rag-service means it holds
nothing for the datasource. Any other rag-service error deletes nothing and is
the request's answer (`503` while rag-service is down): repeat the delete once
it is back.

The datasource's chunk statistics subtract what a write replaced
(`chunks_replaced` in rag-service's answer) and what the retire removed. They
can end up too low by the chunks of a write that rag-service stored and then
reported as failed. Chunks written before record keys existed are never
replaced: run one `full_refresh` + `overwrite` sync per datasource after the
upgrade; its retire removes them.

To see what a datasource is doing:

```sql
SELECT id, status, trigger, worker_id, heartbeat_at, started_at, finished_at, error
FROM connector_sync_jobs
WHERE datasource_id = '<datasource id>'
ORDER BY created_at DESC
LIMIT 5;
```

`GET /api/v1/datasources/{id}/sync-history` returns the same rows, and the
datasource's `last_error` carries the reason of the last failed job. That text
is stored without credentials: the query string of any URL in it, the password
of a URL's user and the values of the connector's secret fields are replaced by
`***`. The service log keeps the exception as it was raised.

## API reference

Use [api.md](api.md) for the human-maintained endpoint contract. The
`openapi.json` file is generated and must not be treated as default reading
material for planning tasks.
