# connector-py

Generic, pluggable **source → destination** connector framework. It runs data
syncs in-process, without Docker:

| Capability                          | Where                                                     |
|-------------------------------------|-----------------------------------------------------------|
| Source definitions catalog          | `ConnectorRegistry.list()` (+ entry-point discovery)      |
| Connector spec (JSON Schema)        | `BaseConnector.spec()` derived from a pydantic `Config`; carries `category` and `icon_svg` |
| Check connection                    | `check()`; `check_connection()` never raises              |
| Discover schema                     | `BaseSource.discover()` → `Catalog`                       |
| Read records / incremental state    | `BaseSource.read()` yielding `Record` / `State`           |
| Incremental cursors and checkpoints | `connector.common.cursor.CursorTracker`                   |
| Batches over HTTP                   | `HttpBatchDestination` (JSON batch payload to any endpoint) |
| Connection + sync job               | `Connection`, `SyncRunner`, `Job`                         |
| Connectors built per job            | `ConnectorFactory` (default: `RegistryConnectorFactory`)  |
| Job observers                       | `SyncOptions(progress_hook=..., status_hook=...)`         |
| Cron / interval schedule            | `SyncScheduler` + `Schedule.cron()` / `Schedule.every()`  |
| Source preview                      | `BaseSource.preview()`                                    |
| Connector icons                     | `BaseConnector.icon_svg()` / `registry.icon()`            |
| One live job per connection         | `SyncAlreadyRunningError`; `ExclusiveJobStore`            |
| Job timeout                         | `SyncOptions(timeout_seconds=...)`                        |
| Bounded number of parallel syncs    | `SyncOptions(max_concurrent_jobs=...)`; the rest wait as PENDING |
| Shutdown without losing work        | `SyncRunner.shutdown()` leaves jobs resumable for the next start |
| Check before sync                   | `SyncOptions(check_before_sync=True)`                     |
| Failed-on-restart job cleanup       | `SyncScheduler.start()` recovers and resumes interrupted jobs |
| Durable state across restarts       | `connector.stores_sql.SqlStores` (PostgreSQL / SQLite)    |
| Reset / full refresh                | `runner.run(conn, full_refresh=True)`; store `reset()`    |
| Typed errors                        | `connector.errors`, all under `ConnectorError`            |

Deliberately **not** provided: Docker-isolated connector containers,
dbt/normalization, and separate worker pods. Syncs run in the calling
process; for heavy workloads run `SyncRunner` in a dedicated worker deployment
(same package, DB-backed stores) rather than inside the API pod.

## Design

The package is split by responsibility and every extension point is an
abstraction, so new behaviour is added by *adding* classes, not editing them:

| Module          | Responsibility                                      | Extend by                                   |
|-----------------|-----------------------------------------------------|---------------------------------------------|
| `base.py`       | `BaseConnector` → `BaseSource` / `BaseDestination`  | subclassing                                 |
| `registry.py`   | what connectors exist                               | `register()`, entry points                  |
| `visibility.py` | which connectors are exposed *right now*            | any `VisibilitySource` / `VisibilityPolicy` |
| `factory.py`    | where the runner gets the connectors of a job       | any `ConnectorFactory`                      |
| `sync.py`       | moving batches, retries, job bookkeeping            | `SyncOptions`, stores, hooks                |
| `stores.py`     | state, job, connection and schedule store protocols | DB-backed implementations                   |
| `scheduler.py`  | durable cron / interval runs, restart recovery      | any `ScheduleStore`; `tick()` from a CronJob |
| `stores_sql.py` | SQLAlchemy stores + `Cipher` for configs at rest     | other databases via the store protocols     |
| `errors.py`     | the exception hierarchy                             | –                                           |
| `extras.py`     | optional drivers: `require_extra()`                 | –                                           |
| `common/`       | shared bases and helpers: `declarative`, `rest_source`, `graphql`, `microsoft_graph`, `google_auth`, `oauth2`, `s3_connection`, `folder_tree`, `file_system`, `file_formats`, `cursor`, `tabular`, `blocking`, `json_schema` | subclass / reuse in new connectors |

`SyncRunner` depends only on `BaseSource`, `BaseDestination`, a
`ConnectorFactory` and the store protocols. Each protocol lists what the
framework itself calls, nothing more. Services inject SQLAlchemy-backed stores;
the framework ships in-memory ones.

The package is typed (`py.typed`) and checked with mypy.

## Writing a connector

```python
from pydantic import BaseModel, Field
from connector import BaseSource, Catalog, CheckResult, ConfiguredCatalog, ConnectorDefinition
from connector import ConnectorCategory, ConnectorKind, Record, State, Stream, SyncMode, SyncState, secret_field
from connector.common.cursor import CursorTracker

class MyApiConfig(BaseModel):
    base_url: str
    api_key: str = secret_field()            # rendered as password, masked on read-back
    page_size: int = Field(default=100, ge=1)

class MyApiSource(BaseSource[MyApiConfig]):
    definition = ConnectorDefinition(
        name="my_api", display_name="My API", kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.API, tags=frozenset({"api", "experimental"}),
    )
    Config = MyApiConfig

    @classmethod
    def supported_sync_modes(cls): return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def check(self) -> CheckResult: ...
    async def discover(self) -> Catalog: ...
    async def read(self, catalog: ConfiguredCatalog, state: SyncState | None = None):
        for cs in catalog.streams:
            name = cs.stream.name
            tracker = CursorTracker(name, state, enabled=cs.sync_mode is SyncMode.INCREMENTAL)
            async for row in self._fetch(name, since=tracker.start):   # None: first or full run
                tracker.observe(row.get("updated_at"))
                yield Record(stream=name, data=row)
            if final := tracker.final_state():
                yield final                                              # checkpoint
```

That is the whole contract. `spec()`, `from_config()`, `validate_config()`,
`mask_config()`, `check_connection()` and `preview()` come for free.

A mapping that holds credentials next to ordinary settings (request headers,
query parameters, driver options) is declared with `sensitive_mapping_field()`
instead of `Field()`. Its keys stay readable; what a key named like a
credential holds (`Authorization`, `X-Api-Key`, `client_secret`, `token`,
`password`, ...; see `connector.redaction.is_sensitive_key`) is masked by
`mask_config()` at any depth, and the spec flags the field `x-sensitive-keys`.
The name is all there is to go by: a credential kept under a key that does not
say so is shown. Mappings that name tables or columns stay plain `Field()`s.

The configuration model is named by the type parameter, by `Config`, or by
both; where both are given they must agree (a `TypeError` at class creation
otherwise). `Config` agrees when it is the declared model or derived from it,
so a subclass of a concrete connector may narrow its parent's model.

`check()` reports the failures it expects as `CheckResult(ok=False, ...)`.
Callers that want a verdict and never an exception use `check_connection()`.
When the external system answers with something a sync cannot use (a rejected
token request, an error inside a `200` response) raise `SourceError`; leave
transport errors of `httpx` or a driver as they are. Import optional drivers
where they are first needed, through `connector.extras.require_extra()`, so a
missing one becomes a `MissingExtraError` that names the extra to install.

### Incremental cursors

`connector.common.cursor` holds the bookkeeping every incremental source needs.
The stored state of a stream is always `{"cursor": value}`.

| Helper | Use |
|---|---|
| `incremental_cursor(configured)` | the configured cursor field, or `None` when the stream is not read incrementally |
| `CursorTracker(stream, state, enabled=..., ordered=..., checkpoint_every=...)` | `start` (where the last run stopped), `observe(value)` per record, `final_state()` at the end |
| `is_newer(a, b)` / `later(a, b)` | the one comparator for ISO timestamps, epochs and ids (integers are compared exactly, so 64-bit ids are safe) |

Two kinds of streams exist:

- **Unordered** (most APIs): records arrive in any order. The cursor is the
  latest value seen and is only known when the stream ends. A timestamp cursor
  is held back to the start of the read minus `CURSOR_SKEW_SECONDS` (5 min):
  a record written to a part already read (a mailbox, a project, an earlier
  page) while the rest was read, or stamped by a clock ahead of ours, is then
  read by the next run instead of never. Record keys absorb what is read twice.
- **Ordered** (`ordered=True`): the source sorts by the cursor, as in
  `WHERE cursor > ? ORDER BY cursor`. The last value read is the new cursor,
  and with `checkpoint_every=N` the tracker hands back a `State` from
  `observe()` about every N records. Yield it *before* the record:

```python
tracker = CursorTracker(name, state, enabled=cursor is not None, ordered=True,
                        checkpoint_every=CHECKPOINT_ROWS)
async for row in rows:                       # ORDER BY cursor
    if checkpoint := tracker.observe(row[cursor]):
        yield checkpoint
    yield Record(stream=name, data=row)
if final := tracker.final_state():
    yield final
```

A mid-stream checkpoint only ever names a value whose rows have all been
delivered: it is emitted once the value changes, so a resumed
`WHERE cursor > saved` skips nothing. Pass `exact=False` to `observe()` for a
value Python cannot compare the way the source sorts it (text under a
collation); it still moves the cursor but is never used as a checkpoint
boundary. A sync that dies in the middle of a large stream resumes near where
it stopped. The SQL family checkpoints every 10 000 rows
(`common.tabular.CHECKPOINT_ROWS`), file sources every 25 files.

`common/tabular.py` has the rest of what table-shaped sources share:
`table_stream()`, identifier quoting (`ansi_ident`, `backtick_ident`,
`bracket_ident`; names come from configuration and discovery and are never
interpolated raw) and value conversion (`to_json_scalar`, `to_json_value`,
`from_json_scalar`). A stored cursor does not carry its column's type:
`from_json_scalar` sends any text that parses as an ISO date or time back as a
timestamp, so a text column whose values look like dates (`20240101`) cannot
serve as a cursor. Use a temporal or numeric column.

`common/blocking.py` drains a blocking iterator (a driver cursor, lazily parsed
rows) in a worker thread. A consumer that is cancelled or times out while a
chunk is being fetched waits for that fetch (the thread cannot be interrupted)
and the iterator is closed whichever way the consumer leaves.
`common/json_schema.py` infers a schema from sample records. Stream schemas are
best-effort: empty `properties` means "not declared", not "no fields".

REST sources share `common/rest_source.py`: retry on `429`/`5xx` (a `429`, or
a `403` with `x-ratelimit-remaining: 0`, waits for `Retry-After` or
`x-ratelimit-reset`, up to an hour, and gets more attempts), and
`split_query()` for an address that carries a query string of its own (httpx
drops it once `params` are passed). The client a source builds follows
redirects unless the class sets `follow_redirects = False`, as `http_json`
does: its address and headers are free text, and a redirect would carry the
headers to another host. Graph delta queries (`GraphSource.delta(path,
resume_from=stored_link)`) start over from `path` when the stored link has
expired (`410 Gone`).

Register it explicitly:

```python
from connector import default_registry
default_registry.register(MyApiSource)
```

or ship it in any installed package and let the registry find it:

```toml
[project.entry-points."connector.sources"]
my_api = "my_pkg.sources:MyApiSource"
```

```python
default_registry.load_entry_points()
```

An entry point that cannot be imported or registered is logged and skipped, so
one broken plugin does not take the catalog down; `load_entry_points(strict=True)`
raises instead.

## Runtime visibility

The registry never decides visibility itself. A `VisibilityPolicy` is asked on
**every** `list()` / `get_*()` call, so changes apply without restart.
`default_policy()` layers, highest precedence first:

1. `RuntimeOverrides` – in-memory, for an admin API: `registry.set_enabled("postgres", False)`
2. `FileVisibilitySource` – JSON/YAML file, re-read when its mtime changes
3. `EnvVisibilitySource` – `CONNECTOR_ENABLED`, `CONNECTOR_DISABLED`,
   `CONNECTOR_DEFAULT`, `CONNECTOR_TAGS_ENABLED`, `CONNECTOR_TAGS_DISABLED`
4. static defaults passed in code

Rule file shape (names accept `fnmatch` globs; explicit `disabled` always wins):

```json
{
  "default": "enabled",
  "enabled": ["postgres", "http_*"],
  "disabled": ["jsonl_file"],
  "tags": { "disabled": ["experimental"] }
}
```

```python
from connector import ConnectorRegistry, RuntimeOverrides, default_policy

registry = ConnectorRegistry(
    policy=default_policy(overrides=RuntimeOverrides(), config_file="configs/connectors.json"),
)
registry.set_enabled("postgres", False)   # finds the RuntimeOverrides inside the policy
```

Hidden connectors are excluded from `list()`, reported with
`is_available=False` in `list(include_hidden=True)`, and raise
`ConnectorDisabledError` from `get_source()` / `get_destination()`; a sync job
of such a connection fails with that error. Internal code can still resolve
them with `allow_hidden=True` (for the runner:
`SyncOptions(connector_factory_allow_hidden=True)`).

## Running a sync

```python
from connector import ConfiguredCatalog, Connection, SyncOptions, SyncRunner

src = registry.get_source("postgres").from_config(cfg)
catalog = ConfiguredCatalog.from_catalog(await src.discover(), sync_mode=SyncMode.INCREMENTAL)

conn = Connection(
    name="crm", source_name="postgres", source_config=cfg,
    destination_name="http_batch",
    destination_config={"base_url": "http://ingest.internal:8080", "batch_path": "/ingest/batch",
                        "datasource_id": ds_id, "connector_type": "postgres"},
    catalog=catalog,
)
runner = SyncRunner(registry, state_store=my_db_state_store, job_store=my_db_job_store,
                    options=SyncOptions(batch_size=200))
job = await runner.run(conn)          # or: await runner.start(conn) -> background Job
```

Memory is bounded by `batch_size` per stream; each batch is released once the
destination acknowledges it. `State` items from the source are checkpointed
only after the preceding records were written.

### Where the connectors come from

The first argument of `SyncRunner` is a registry or any `ConnectorFactory`:

```python
class ConnectorFactory(Protocol):
    async def source(self, connection: Connection) -> BaseSource: ...
    async def destination(self, connection: Connection) -> BaseDestination: ...
```

Given a registry, the runner wraps it in `RegistryConnectorFactory`: the class
comes from the registry and the configuration from `connection.source_config` /
`destination_config`. A host writes its own factory when that is not where
configurations live, for example to keep credentials out of the stored
connection and fetch them only when a job runs:

```python
class VaultConnectorFactory:
    def __init__(self, registry: ConnectorRegistry, vault: Vault) -> None:
        self.registry, self.vault = registry, vault

    async def source(self, connection: Connection) -> BaseSource:
        config = await self.vault.read(connection.metadata["config_id"])
        return self.registry.get_source(connection.source_name).from_config(config)

    async def destination(self, connection: Connection) -> BaseDestination:
        return self.registry.get_destination(connection.destination_name).from_config(
            connection.destination_config
        )

runner = SyncRunner(VaultConnectorFactory(registry, vault), job_store=..., state_store=...)
```

The factory is called once per job, when the job starts running. What it
raises fails that job (`job.error`), like any other failure of the run. The
runner closes both connectors when the job ends.

### Jobs

`run()` executes a connection and returns the finished `Job`; `start()` returns
the `PENDING` job at once and runs it in the background (`wait(job_id)`,
`cancel(job_id)`, `shutdown()`). A job ends `SUCCEEDED`, `FAILED` or
`CANCELLED`. A failed run does not raise: the job carries
`error = "<ExceptionType>: <message>"`, and `job.stats[stream]` counts
`records_read`, `records_written` and `batches`.

`job.error` is stored and usually shown to people who may not see the
connector's configuration, so credentials are taken out of it
(`connector.redact_secrets`): the query string of a URL, the password of a
URL's user, and the secrets of the run's source and destination
(`secret_values()`: their secret fields, and what the credential keys of their
sensitive mapping fields hold) become `***`. The log keeps the exception as it
was raised.

Two observers can be set on `SyncOptions`:

| Hook | Called |
|---|---|
| `status_hook(job)` | once per status: `PENDING` when the job is created (before `start()` returns), `RUNNING`, then its final status. A start that is refused reports nothing |
| `progress_hook(job)` | after every persisted step: each batch and each status change |

An exception raised by a hook is logged and the sync goes on. With
`max_concurrent_jobs` the slot is kept through the final hooks, so post-sync
work done there is covered by the limit as well. Jobs the runner closes for a
worker that is gone (see below) are reported to the hooks like any other.

What surrounds a sync does not decide its outcome, and cannot keep later jobs
from running:

- A heartbeat the job store refuses is logged and the next one is tried.
- The final status is written with `SyncOptions.retry`. Whether or not that
  succeeds, the connection and the concurrency slot are released.
- A `close()` that fails, or a source whose `read()` generator fails while it is
  being closed, is logged; the job keeps the outcome of the run itself.
- `timed out after <n>s` is reported only when `timeout_seconds` fired. The limit
  covers the whole job - building and opening the connectors, the preflight check
  and the sync. A `TimeoutError` raised by a connector is that connector's failure.
- `cancel()` ends a job `CANCELLED` even if it had not started executing yet.
  Cancelling a task that awaits `wait()` leaves the job running.

### One live job per connection

`run()` and `start()` raise `SyncAlreadyRunningError` (`connection_id`,
`job_id`, `worker_id`) when the connection already has a live job: one in this
process, or one in the job store whose heartbeat is younger than
`SyncOptions.stale_after_seconds`. A non-terminal job with an older heartbeat
was left by a process that is gone; it is marked `FAILED` and the new job
starts. Should that process only have been silent, its next heartbeat raises
`JobTakenOverError` from the job store (a live status is never written over a
terminal one) and the runner ends its run `FAILED` ("superseded: ...") without
touching the store's verdict.

Check-then-create leaves a gap two replicas can both pass. A job store that
also implements `ExclusiveJobStore.create_exclusive()` closes it, and the
runner uses it when present. `InMemoryJobStore` and `SqlJobStore` implement it;
on PostgreSQL add a partial unique index on the connection id for non-terminal
statuses to make it strict under `READ COMMITTED` (`SqlStores` does not create
it, because it would forbid `allow_concurrent_jobs`).
`SyncOptions(allow_concurrent_jobs=True)` turns the guard off.

### Writing a destination

```python
class MySink(BaseDestination[MySinkConfig]):
    definition = ConnectorDefinition(name="my_sink", display_name="My sink",
                                     kind=ConnectorKind.DESTINATION)

    async def check(self) -> CheckResult: ...
    async def begin(self, catalog, connection_id=None, *, job_id=None) -> None: ...
    async def write(self, batch: Batch) -> WriteResult: ...
    async def finalize(self, catalog, connection_id=None, *, job_id=None) -> None: ...
    async def abort(self, catalog, connection_id=None, *, job_id=None, error=None) -> None: ...
```

Only `check` and `write` are required. One run calls `begin`, then `write` per
batch, then `finalize` once every batch was written. `abort` is called instead
when the run failed, timed out, was cancelled or was interrupted by a shutdown
after `begin` (a failing `finalize` included). It may release what the run
holds open, but it must not discard batches `write` already acknowledged:
their checkpoints are stored as the run progresses, and the next run continues
after them. An exception `abort` raises is logged without replacing the
original failure. `job_id` is the same in all of them and in `Batch.job_id`.

- `(job_id, stream, batch_index)` identifies a batch across retries; make
  `write` idempotent on it where possible.
- A failed `write` is retried per `SyncOptions.retry` (`RetryPolicy`: 3
  attempts, exponential backoff) and then fails the job with
  `DestinationWriteError`. A destination that raises `DestinationWriteError`
  itself says retrying is pointless, and the run stops at once.
- `needs_final_batch = True` asks for a closing `is_last` batch per stream even
  when it is empty, for a receiving end that waits for an end-of-stream marker
  (`http_batch` sets it). Other destinations receive non-empty batches only,
  and `job.stats[stream].batches` counts what was sent.

### Errors

Every error the package raises on purpose derives from `ConnectorError`. Errors
of the libraries underneath (`httpx`, database drivers) are not wrapped.

| Error | Raised when |
|---|---|
| `ConnectorNotFoundError`, `ConnectorDisabledError`, `DuplicateConnectorError` | registry lookup and registration |
| `ConfigValidationError` | a configuration does not fit the connector's model; `.errors` holds `{"type", "loc", "msg"}` entries and never the submitted values |
| `MissingExtraError` (also an `ImportError`) | an optional driver is not installed; the message names the extra |
| `CheckFailedError` | `check_before_sync` is on and the source or destination check said no |
| `StreamNotFoundError` | a requested stream is not in the discovered catalog |
| `SourceError` | the external system answered, but not with what a sync can use |
| `DestinationWriteError` | a batch could not be written |
| `SyncAlreadyRunningError`, `JobNotFoundError` (both `SyncError`) | starting or looking up a job |

## Scheduling and durability

Nothing the framework needs to remember lives only in memory. Four stores hold
it, and `connector.stores_sql` provides all four on SQLAlchemy (PostgreSQL in
production, a SQLite file on a single node):

| Store | Holds | Why it matters after a restart |
|---|---|---|
| `ConnectionStore` | connections incl. connector configs (encrypted with a `Cipher`) | the catalog of what to sync |
| `StateStore` | incremental cursors, saved at every `State` checkpoint | a killed sync continues where it stopped |
| `JobStore` | job status, stats, `worker_id`, `heartbeat_at`, `trigger` | history survives; dead jobs are detectable |
| `ScheduleStore` | `next_run_at` / `last_run_at` per connection | missed runs are caught up, not forgotten |

A host with its own tables implements the protocols of `connector.stores`
instead. Each lists only what the framework calls:

| Protocol | Methods |
|---|---|
| `StateStore` | `load`, `save` |
| `JobStore` | `create`, `update`, `get`, `list_active` |
| `ExclusiveJobStore` (optional) | `JobStore` + `create_exclusive` |
| `ConnectionReader` | `get`, `list` (all the scheduler needs; `ConnectionStore` adds `create`, `update`, `delete`) |
| `ScheduleStore` | `get`, `upsert`, `delete`, `list`, `list_due`, `claim` |

```python
from connector import Schedule, SyncOptions, SyncRunner, SyncScheduler
from connector.stores_sql import FernetCipher, SqlStores

stores = SqlStores(settings.DATABASE_URL, cipher=FernetCipher(settings.ENCRYPTION_KEY))
await stores.create_tables()                      # or create them in an Alembic migration

runner = SyncRunner(registry, state_store=stores.states, job_store=stores.jobs,
                    options=SyncOptions(stale_after_seconds=300))
scheduler = SyncScheduler(runner, stores.connections, stores.schedules,
                          poll_interval_seconds=15, misfire="run_once",
                          resume_interrupted=True, replicated=True)

resumed = await scheduler.start()                 # app startup (FastAPI lifespan)
...
await scheduler.stop()                            # app shutdown
```

### Schedules

A connection re-runs on its own when it has a `Schedule`: a cron expression or a
fixed period chosen by the user.

```python
conn.schedule = Schedule.cron("0 3 * * *", timezone="Europe/Istanbul")  # needs [scheduler]
conn.schedule = Schedule.every(minutes=30)                              # no extra dependency
conn.schedule = Schedule.every(hours=6, run_on_create=True)             # first run right away
await stores.connections.update(conn)
await scheduler.schedule(conn)        # call after every create / update of a connection
await scheduler.unschedule(conn.id)   # or set schedule.enabled = False
```

Combine a schedule with `SyncMode.INCREMENTAL` and every run only fetches what
changed since the previous one. Editing unrelated fields keeps the pending slot;
changing the timing resets it. Interval schedules advance from the previous slot,
so they do not drift with polling delay or job duration.

### What happens on restart

`scheduler.start()` does three things before it begins polling:

1. **Reconciles** schedule entries with the stored connections.
2. **Recovers** jobs a dead process left `PENDING` or `RUNNING`: they become
   `FAILED` ("interrupted by service restart"). With several replicas pass
   `replicated=True`: only jobs whose heartbeat is older than the runner's
   `stale_after_seconds` are considered dead, so a live sibling's work is left
   alone, and the check repeats on every poll, which also catches a worker
   that died later.
3. **Resumes** those connections (`trigger="resume"`). The new job starts from
   the last saved checkpoint, not from zero. A connection that cannot be
   resumed is logged; the others are resumed and polling starts all the same.

Runs that came due while the service was down fire once (`misfire="run_once"`)
or wait for the next slot (`misfire="skip"`).

### Several replicas

Before starting a run the scheduler claims the slot with a compare-and-set on
`next_run_at`; exactly one replica wins. `SyncRunner` also refuses to start a
connection that a live sibling is already syncing
([one live job per connection](#one-live-job-per-connection)). The scheduler
treats that `SyncAlreadyRunningError` as "nothing to do"; any other failure to
start a run is logged as an error, does not stop the other due runs, and gives
the slot back so that the next poll tries again.
`scheduler.tick()` is public, so a Kubernetes CronJob can drive scheduling
instead of the in-process loop.

## Built-in connectors

69 sources and 4 destinations. Most SaaS sources are declarative (`common/declarative.py`): a list of `StreamSpec` objects plus a pagination strategy. Sources without an extra need only the core dependencies (`pydantic`, `httpx`).

### Knowledge bases and wikis

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `axero` | Axero | – | articles, blogs and wiki pages, plus spaces |
| `bookstack` | BookStack | – | shelves, books, chapters and pages (with HTML/markdown body) |
| `canvas` | Canvas LMS | – | courses and, per course, pages, assignments and announcements |
| `coda` | Coda | – | docs and, per doc, pages and tables |
| `confluence` | Confluence | – | Confluence source (Cloud and Data Center) over the REST v1 content API |
| `discourse` | Discourse | – | categories, topics and posts |
| `document360` | Document360 | – | project versions and their articles (with HTML content) |
| `gitbook` | GitBook | – | spaces of an organization and their pages (markdown body) |
| `google_sites` | Google Sites | – | Google Sites source |
| `guru` | Guru | – | cards (with HTML content flattened to text) and collections |
| `loopio` | Loopio | – | library entries (question / answer pairs) via OAuth2 client credentials |
| `lumapps` | LumApps | – | published content of an instance (``content/list``) |
| `mediawiki` | MediaWiki | – | MediaWiki source (any wiki running MediaWiki, including Wikipedia) |
| `notion` | Notion | – | Notion source |
| `outline` | Outline | – | collections and documents (markdown text included by the API) |
| `sharepoint` | SharePoint Online | – | SharePoint Online source via Microsoft Graph |
| `slab` | Slab | – | posts and topics |
| `wikipedia` | Wikipedia | – | the MediaWiki reader pointed at a language edition |

### Business suites

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `microsoft365` | Microsoft 365 | – | directory, OneDrive files and OneNote pages |

### Object and cloud storage

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `s3` | Amazon S3 | `s3` | boto3) |
| `box` | Box | – | Box source |
| `cloudflare_r2` | Cloudflare R2 | `s3` | the S3 reader with Cloudflare R2 connection settings |
| `dropbox` | Dropbox | – | Dropbox source |
| `egnyte` | Egnyte | – | Egnyte source |
| `google_storage` | Google Cloud Storage | `s3` | the S3 reader with Google Cloud Storage connection settings |
| `google_drive` | Google Drive | `google` | Google Drive source |
| `minio` | MinIO | `minio` | MinIO source |
| `oracle_storage` | Oracle Object Storage | `s3` | the S3 reader with Oracle Object Storage connection settings |

### Files

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `file_server` | File Server (SMB / network share) | `smb` | a Windows / Samba share over SMB, or a mounted network path |
| `file_upload` | File Upload | – | files that were uploaded to (or mounted into) a local directory |
| `ftp` | FTP / FTPS | – | files over FTP, optionally with explicit TLS (standard library only) |
| `jsonl_file` | JSON Lines Files | – | JSON Lines file source |
| `sftp` | SFTP | `sftp` | files over SSH with password or private-key authentication |

### Ticketing and work management

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `airtable` | Airtable | – | one stream per table of a base |
| `asana` | Asana | – | projects and their tasks (incremental via ``modified_since``) |
| `clickup` | ClickUp | – | spaces and tasks of a workspace (team) |
| `freshdesk` | Freshdesk | – | tickets, contacts, companies and the solutions knowledge base |
| `jira` | Jira | – | Jira source (Cloud and Data Center) |
| `linear` | Linear | – | teams, projects and issues with their comments |
| `productboard` | Productboard | – | products, components, features and notes |
| `testrail` | TestRail | – | projects, suites and test cases |
| `zendesk` | Zendesk | – | support tickets (+ comments) and Help Center articles |

### Messaging and e-mail

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `discord` | Discord | – | text channels of a guild and their messages |
| `imap` | Email (IMAP) | – | Generic e-mail source over IMAP (standard library only) |
| `gmail` | Gmail | `google` | Gmail source (service account with domain-wide delegation, or an access token) |
| `microsoft_teams` | Microsoft Teams | – | Microsoft Teams source via Microsoft Graph |
| `outlook` | Outlook (Microsoft 365) | – | Outlook (Exchange Online) source via Microsoft Graph |
| `slack` | Slack | – | channels, users and channel messages |
| `xenforo` | XenForo | – | forums (nodes), threads and posts through the REST API (XF 2.1+) |
| `zulip` | Zulip | – | streams (channels) and messages |

### Sales and meetings

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `fireflies` | Fireflies.ai | – | meeting transcripts with summary and full text |
| `gong` | Gong | – | users, calls and call transcripts |
| `highspot` | Highspot | – | spots and the items (content) inside each spot |
| `hubspot` | HubSpot | – | CRM objects (contacts, companies, deals, tickets by default) |
| `salesforce` | Salesforce | – | one stream per configured sObject, read with SOQL |

### Code repositories

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `bitbucket` | Bitbucket | – | repositories of a workspace, their pull requests and issues |
| `github` | GitHub | – | repositories, issues, pull requests |
| `gitlab` | GitLab | – | GitLab source (gitlab.com or self-managed) over the REST v4 API |

### Databases

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `mssql` | Microsoft SQL Server | `mssql` | base tables of one database, read with pyodbc |
| `mongodb` | MongoDB | `mongodb` | pymongo >= 4.9 with its async client) |
| `mysql` | MySQL | `mysql` | aiomysql) |
| `postgres` | PostgreSQL | `postgres` | asyncpg) |

### Warehouses

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `spark` | Apache Spark | `spark` | tables and ad-hoc SQL of a Spark cluster, read remotely |
| `clickhouse` | ClickHouse | – | ClickHouse source over the native HTTP interface (no driver dependency) |

### Search engines

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `elasticsearch` | Elasticsearch | – | every index (or the configured ones) as a stream |
| `opensearch` | OpenSearch | – | the Elasticsearch reader with OpenSearch connection settings |

### Event streaming

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `kafka` | Apache Kafka | `kafka` | one stream per topic, read up to the current end of each partition |

### Generic APIs

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `http_json` | HTTP JSON API | – | Generic HTTP JSON API source |

### Other

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `braintrust` | Braintrust | – | projects, experiments, datasets (+ their rows) and prompts |

### Destinations

| Name | Connector | Extra | Summary |
|---|---|---|---|
| `http_batch` | HTTP Batch Ingestion | – | POSTs each batch as JSON to a configurable endpoint |
| `memory` | In-Memory (testing) | – | tests and dry runs |
| `minio` | MinIO | `minio` | same writer as `s3` with MinIO connection settings |
| `s3` | Amazon S3 | `s3` | JSONL (optionally gzip) parts + manifest per run |

### Writing a declarative source

```python
class AcmeSource(DeclarativeRestSource[AcmeConfig]):
    definition = ConnectorDefinition(name="acme", display_name="Acme", ...)
    Config = AcmeConfig

    def base_url(self): return "https://api.acme.com"
    def auth_headers(self): return {"Authorization": f"Bearer {self.config.token}"}

    def streams(self):
        return [
            StreamSpec(name="projects", path="/projects", records_path="data",
                       paginator=CursorPagination(cursor_path="next", cursor_param="cursor")),
            StreamSpec(name="tasks", path="/projects/{parent[id]}/tasks", records_path="data",
                       parent="projects", parent_field="project_id", per_parent_cursor=True,
                       cursor_field="updated_at", incremental_param="updated_since"),
        ]
```

Paginators: `OffsetPagination`, `PageNumberPagination`, `CursorPagination`,
`LastRecordPagination`, `NextUrlPagination`, `LinkHeaderPagination`,
`ContinueParamsPagination`. Per-stream hooks: `transform`, `expand` (one item to many
records), `detail_path` (fetch the body per record), `enrich` (async method),
`on_request` (unusual filter syntax), `error_check` (APIs that answer 200 with an error).
The engine stops when an API serves the same page twice, skips child requests that
answer 403/404, and applies client-side incremental filters before detail requests.
`stop_when_page_seen=True` ends a client-side-filtered read at the first page that is
entirely older than the cursor, for lists the API orders by the cursor field newest
first (GitHub pull requests, XenForo threads, Discourse topics); a list ordered by id
(Discourse posts) is still walked in full, as an old item edited later sits anywhere in it.
Parent streams are read page by page as a child consumes them; only a parent shared
by several configured children is kept for the siblings, cut down to the fields they
refer to (`parent_key`, `{parent[...]}` placeholders), and dropped after the last one.
`parent_uses_cursor=True` reads the parents with the child's cursor - for APIs where a
child changes its parent's modification marker (a comment moves its ticket's
`updated_at`), an incremental run then visits only the parents that gained children.

## Icons

Each built-in connector ships a 24×24 SVG in `connector/icons/`. Brand marks are
the [Simple Icons](https://simpleicons.org) glyphs (CC0) filled with the brand
colour; protocol-level connectors (FTP, IMAP, file upload ...) and brands that
are not in Simple Icons keep a generic `stroke="currentColor"` drawing that
follows the UI theme (a letter monogram for a brand, as in `gong.svg`). `connector/icons/ATTRIBUTION.md` lists the provenance of
every file; the logos remain trademarks of their owners and each brand's usage
guidelines apply. Expose an icon from a service as `image/svg+xml`:

```python
@router.get("/connectors/{name}/icon.svg")
async def icon(name: str):
    svg = registry.icon(name, ConnectorKind.SOURCE)
    if svg is None:
        raise HTTPException(404)
    return Response(svg, media_type="image/svg+xml")
```

`ConnectorInfo.has_icon` tells the frontend whether to request it. Third-party
connectors set `icon="my_pkg.assets:name.svg"` on their definition or override
`icon_svg()`.

## Install

```toml
# apps/<service>/pyproject.toml
dependencies = ["connector-py[scheduler,postgres]"]
[tool.uv.sources]
connector-py = { path = "../../packages/connector-py" }
```

## Development

```bash
cd packages/connector-py
uv sync --all-extras
uv run pytest
uv run ruff check src tests
uv run mypy
```
