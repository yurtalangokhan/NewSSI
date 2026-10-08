# Backend Observability Contract

All backend services (`agent-service`, `user-service`, `rag-service`,
`tools-service`) share one observability package, `packages/observability`. The
package owns the mechanism: the record schema, the formatters, the destinations,
the correlation context, dependency state, and startup retry. Each service keeps
a thin binding in its own `core/observability` module that owns only the service
names: which environment variables feed the configuration, the service name
stamped on records, and its own noisy-logger policy.

A service uses logging through three calls:

- `configure_logging(...)` — the binding maps the service's environment onto one
  `LoggerConfig` and calls the package's `configure` once at startup.
- `get_logger(name)` — return a standard logger; this is the call most modules make.
- `CorrelationMiddleware` — installed outermost, so every record written while
  handling a request carries the same correlation id without any call site
  passing one.

The package also exports the dependency-health and retry API:

- `DependencyPolicy`, `DependencyStatus`, `DependencyRegistry` — dependency state
  tracking with a module-level `dependency_registry` singleton per service.
- `readiness_payload(service_name=...)` — build the readiness response body.
- `retry_async()` / `retry_sync()` — bounded startup retries.
- `sanitize_exception()` / `dependency_error_fields()` — safe structured log
  fields for exceptions.

New code must import loggers from the service binding, not from `logging`
directly. Modules that still call `logging.getLogger(...)` continue to receive
the centralized root formatter, but they are tracked for migration to the
stricter single-module import rule.

## Logging contract

Every backend service emits the same field set, defined once in the package as
`RECORD_FIELDS` and rendered by one `JsonFormatter` and one `TextFormatter` that
share a single field builder. A dashboard query or an index mapping written
against one service works against every service and every destination. Absent
values are written as `null`, never omitted, so a consumer never has to test for
key presence. Human-readable text is the default for local development; JSON is
available for containerized environments. Text logs colorize severity for local
terminal readability only; JSON logs never include ANSI color codes.

Required fields:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC ISO-8601 time of the record |
| `level` | Standard library level name |
| `service` | The service name stamped by the binding |
| `logger` | The logger name |
| `event` | The call site's event code, e.g. `startup.dependency.ok` |
| `message` | The human-readable message |
| `request_id` | Correlation id bound by the middleware |
| `trace_id` | Distributed trace id, when a tracer is configured |
| `user_id` | Sanitized actor identifier, when bound |
| `module` / `function` / `line` | Where the record was written |
| `operation` | The operation being performed |
| `dependency` | The dependency the record is about |
| `attempt` / `max_attempts` | Retry position |
| `elapsed_ms` | Duration of the operation |
| `status` | Outcome, e.g. `ok`, `failed`, `starting` |
| `error` | Sanitized exception structure, or `null` |

An exception is reported as a structure, not a rendered traceback:

- `exception_type`
- `exception_message`
- `retryable`
- `hint`

Redaction is not optional and cannot be bypassed by a call site: the formatter
masks values under sensitive keys (`api_key`, `password`, `token`, `secret`,
`authorization`, and their case spellings) and sanitizes exception messages
before any destination sees the record. Logs must not include database
passwords, bearer tokens, API keys, connection URLs with credentials, or
unbounded stack traces in normal startup failure messages. Full stack traces are
reserved for debug logs or final fatal startup failures.

Example text log:

```text
2026-09-01T11:20:42.118Z INFO user-service     Postgres migrations completed. | request_id=... event=startup.dependency.ok dependency=postgres attempt=2/5 elapsed_ms=432 status=ok [startup.py run_migrations 88]
```

Example JSON log:

```json
{
  "timestamp": "2026-09-01T11:20:42.118Z",
  "level": "INFO",
  "service": "user-service",
  "logger": "infrastructure.db.startup",
  "event": "startup.dependency.ok",
  "message": "Postgres migrations completed.",
  "request_id": "6f1c2...",
  "trace_id": null,
  "user_id": null,
  "module": "startup",
  "function": "run_migrations",
  "line": 88,
  "operation": "migrate",
  "dependency": "postgres",
  "attempt": 2,
  "max_attempts": 5,
  "elapsed_ms": 432,
  "status": "ok",
  "error": null
}
```

## Correlation

One request produces one identifier, and every record written while handling it
carries that identifier. `CorrelationMiddleware` is installed outermost in every
service: it preserves an inbound `X-Request-ID` (falling back to
`X-Correlation-ID`), generates one when neither is present, binds it into a
`ContextVar`, and writes it back onto the response.

The header is untrusted input: it is length-limited to 128 characters and
filtered to a safe character set, so a caller cannot inject a newline that would
forge an extra log record or a field separator that would corrupt the payload.

Outbound calls continue the chain. `observability.outbound_headers()` returns the
current correlation values as headers; agent-service's shared outbound transport
merges them into every request it sends, so one identifier spans every service a
request touches.

## Tracing (OpenTelemetry)

The third pillar sits next to logs and metrics. With `OTEL_ENABLED=false`
(the default) the process produces no spans and pays nothing; with it on, the
correlation middleware opens one server span per request, continues an upstream
trace when the request carries a W3C `traceparent`, and binds the span's trace id
into the log context — so the trace in a tracing UI and its records in
Elasticsearch are joined by one value. An outbound call injects its `traceparent`
the same way, so the chain spans services.

```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_TRACES_SAMPLE_RATIO=1.0        # or lower in busy environments
OTEL_METRICS_ENABLED=true           # optional: push metrics over OTLP
```

Delivery goes to a collector over OTLP/http; the endpoint, credentials, sample
ratio, and export interval are the `OTEL_*` keys in `docs/env-variables.md`.
Sampling is parent-based: a request that arrives inside a sampled trace is
sampled whatever the local ratio says, so one trace is never half-recorded.

### The stack in Compose

The observability platform runs as infrastructure services in
`deploy/docker/docker-compose-services.yml`, every host port loopback-only. The
whole stack is gated behind the `observability` Compose profile: nothing starts
unless it is asked for, and `make stack-up` never pulls it up. Start it with
`make observability-up`, stop it with `make observability-down`:

| Service | Host port | Role |
| --- | --- | --- |
| `otel-collector` | `4318` | Receives OTLP traces and metrics; routes them per `configs/otel-collector/config.yaml` |
| `elasticsearch` | `9200` | Stores logs and traces |
| `kibana` | `5601` | Log and trace workspace |
| `prometheus` | `9090` | Stores scraped and pushed metrics |
| `grafana` | `3001` | Dashboards across all three pillars |

The collector's pipelines are validated against its pinned image and route
traces to Elasticsearch (`otel-traces`) and metrics to Prometheus remote-write.
Logs do not flow through the collector: the services ship them straight to
Elasticsearch through the `elasticsearch` destination. Prometheus scrape targets
are rendered from `configs/prometheus/prometheus.yml.template` by the
`prometheus-config` bootstrap, so the service ports come from `configs/.env`
rather than being hardcoded. Grafana is provisioned with Prometheus and
Elasticsearch datasources from `configs/grafana/provisioning/`.

The pillars are independent, and turning one off never touches the others:

- `OTEL_ENABLED=false` (the default) means the SDK is never loaded and no span
  or metric is produced; logging is unaffected.
- With telemetry on and the collector down, logging still flows to its
  destinations unchanged - the span export fails in the background and the
  request never notices.
- `LOG_OUTPUT=console` with `LOG_FORMAT=json` keeps writing the same records to
  stdout whatever the telemetry decision is.

To switch the whole platform on:

```sh
# in configs/.env
OTEL_ENABLED=true
LOG_OUTPUT=elasticsearch
LOG_EXTERNAL_URL=http://elasticsearch:9200

# then
make observability-up
```

Kibana opens at `http://localhost:5601` and Grafana at
`http://localhost:3001` (admin credentials come from `configs/.env`).

The platform side is provisioned automatically: an `elasticsearch-provision`
bootstrap service runs once after Elasticsearch is healthy and installs the ILM
policy (logs are deleted after `LOG_RETENTION_DAYS`, 30 by default) and two
index templates - `logs-*` with the field contract's identifiers keyword-typed
so filters and aggregations behave consistently, and `otel-traces` with the
trace identifiers keyword-typed so a trace joins to its log records by one
value. The bootstrap is idempotent: every run PUTs the same definitions, so a
restart converges instead of duplicating. No code change is needed to connect
the stack - the environment variables in the switch-on block above are the
whole integration.

Metrics keep both models: the Prometheus scrape endpoint (`/metrics`, the
governance contract) stays, and `OTEL_METRICS_ENABLED=true` additionally pushes
the process's OTel meters to the collector. New business metrics can use either
surface; `observability.counter()` / `observability.histogram()` return no-op
instruments when telemetry is off, so call sites never branch.

## Destinations

A destination is a `logging.Handler` subclass with an explicit lifecycle:
`startup`, `emit`, `flush`, `shutdown`. Every configured destination receives the
same formatter instance, so two destinations cannot disagree about a record.

| Name | Purpose | Options |
| --- | --- | --- |
| `console` | stdout/stderr; the default, collected by the container runtime | `stream`, `level` |
| `file` | Size-rotated file for processes outside a collector | `path`, `max_bytes`, `backup_count`, `level` |
| `syslog` | The host's logging service; the zero-dependency bridge to a collector | `address` (`host:port`), `facility`, `level` |
| `elasticsearch` | The shipped ELK target; delivers through the `_bulk` API | `url`, `index`, `batch_size`, `flush_interval`, `max_queue`, `max_retries`, `retry_backoff`, `shutdown_timeout`, `headers` |
| `external` | Base class for any other log platform reached over the network | `url`, `batch_size`, `flush_interval`, `max_queue`, `max_retries`, `retry_backoff`, `shutdown_timeout`, `headers` |

Failure rules:

- An unknown destination name fails at configuration time, while someone is
  watching, rather than silently discarding every record at 3 a.m.
- A destination that cannot open (an unwritable file path, an unreachable
  syslog socket) disables itself with a reason and the service keeps serving.
- A sink error never propagates to the caller: a logging failure must not take
  down the request that was trying to log.
- The `external` base class queues records and delivers them from a background
  thread: a slow platform applies backpressure to the queue, never to a request.
  A full queue drops the oldest record and counts it, retries are bounded with
  backoff, and a lost batch is reported once through the standard library.

### Shipping to the ELK stack

The shipped platform target is `elasticsearch`. Selecting it is configuration
only — no service code changes:

```env
LOG_FORMAT=json
LOG_OUTPUT=elasticsearch
LOG_EXTERNAL_URL=http://elasticsearch:9200
# Optional:
LOG_EXTERNAL_BEARER_TOKEN=...      # sent as Authorization: Bearer
LOG_ELASTICSEARCH_INDEX=           # unset: one index per service (logs-<service>)
LOG_EXTERNAL_BATCH_SIZE=100
LOG_EXTERNAL_FLUSH_INTERVAL=5.0
```

Behaviour an operator should know:

- Records are delivered through the `_bulk` API as newline-delimited JSON, one
  action and one document line per record, batched (100 records / 5 s by
  default) from a background thread. A slow or down Elasticsearch never blocks a
  request; it fills the bounded queue, and when the queue is full the oldest
  records are dropped and counted.
- With `LOG_ELASTICSEARCH_INDEX` unset, each record lands in
  `logs-<service>` — the `service` field of the record — so one index mapping
  written against the field contract above applies service-wide. Set the
  variable to route everything into one fixed index instead.
- Delivery is at-least-once: a batch whose bulk response reports item failures
  is retried whole, so a partially applied batch can index a record twice.
  Losing an error record during an incident is worse than indexing it twice.
- A refused batch is reported once, with the platform's own reason, through the
  standard library — after the bounded retries are exhausted.

An alternative with no sink at all: keep `LOG_OUTPUT=console` with
`LOG_FORMAT=json` and let a collector (Filebeat autodiscover, Fluent Bit,
Promtail) read the container's stdout. The output is already one JSON object per
line, which is exactly what those collectors ingest.

### Adding another log platform

A target is a subclass of `ExternalSink` that implements one method, `send`,
which delivers a batch of field dictionaries and raises on failure:

```python
from observability import ExternalSink, register_sink

class LokiSink(ExternalSink):
    def send(self, records):
        ...  # POST self.encode_batch(records) to self.url

register_sink("loki", lambda *, formatter, options: LokiSink(formatter=formatter, options=options))
```

A deployment then selects it by name. Adding a platform is a configuration
change, not a change to any service. Selecting the generic `external` name
without registering a target fails at startup, not silently at 3 a.m.

## Configuration flow and design boundaries

Configuration moves in one direction, and each layer owns exactly one kind of
knowledge. Understanding this flow tells you where to change a value, where to
add a setting, and why no layer can grow into a second logging
implementation.

### The one-way flow

1. `configs/.env` is the single environment data file. Only config_manager's
   `load_environment()` reads it; nothing else in the repository touches the
   file.
2. `packages/config-manager/src/config-manager/accessor.py` exposes every key
   as a typed property (`OTEL_ENABLED`, `LOG_FORMAT`, and the rest). Services
   consume values as `env.KEY` and never read `os.environ` directly.
3. The service binding maps names onto values. Each service keeps one binding
   module - `core/observability.py` in user-service and tools-service,
   `core/observability/observability.py` in agent-service, and
   `src/shared/observability.py` in rag-service. Its `logger_config()`
   builds a `LoggerConfig` and its `telemetry_config()` builds a
   `TelemetryConfig` from that service's own environment names. This is the
   only service-specific code in the whole stack.
4. The application entry point calls `configure_logging()` and then
   `configure_telemetry()` once at startup, before serving.
5. `packages/observability/src/observability/otel.py` and `manager.py` turn the
   configuration into running machinery: providers, exporters, formatters, and
   destinations.
6. Runtime consumers read the installed state, never the environment: the
   correlation middleware, the formatters, the outbound hooks, and the metric
   helpers.

### Where each behavior is controlled

| Behavior | Controlled in | Rule |
| --- | --- | --- |
| Telemetry on/off gate | `TelemetryConfig.active` in `otel.py` | Enabled AND an endpoint set; otherwise off |
| Provider setup | `setup_telemetry()` in `otel.py` | Called once at startup; safe to call again |
| Runtime check | `is_enabled()` in `otel.py` | The middleware passes through when false |
| Span per request | `CorrelationMiddleware._traced` in `middleware.py` | Continues an upstream `traceparent` when present |
| Trace id in logs | `_ambient_trace_id` in `formatter.py` | Context value wins; falls back to the active span |
| Outbound propagation | `_fill` in `outbound.py` | Fills only headers the caller did not set |
| Environment keys | `accessor.py` (`OTEL_*`, `LOG_*`) | Typed getters with defaults; no required keys |
| Name-to-value mapping | The binding's `telemetry_config()` / `logger_config()` | The only place service names appear |

### Design boundaries

The layers are held apart by rules, not by convention alone:

- The package reads no environment and imports no service module. A service
  describes itself; the package implements. This is why the same package serves
  four services without branching on which one is calling.
- A binding configures; it does not implement. It must not import a formatter or
  build a handler, and it must call the shared builder and `configure`.
  `scripts/tests/test_observability_bindings.py` enforces this by reading the
  binding sources, so the four services cannot drift back into four
  implementations.
- The OpenTelemetry SDK is reachable only through `otel.py`. Every other module
  imports it lazily, inside a function, and only after `is_enabled()` returns
  true - so a deployment with telemetry off never loads the SDK at all, and the
  cost of the third pillar is zero until it is switched on.
- The dependency direction is one way: application entry point, then binding,
  then package, then SDK. There are no import cycles; the sink registry imports
  `config.py` lazily to keep it that way.

One deliberate tradeoff: the correlation middleware both binds the correlation
context and opens the request span. Splitting those into two middlewares would
need ordered coordination between them to bind the trace id inside the span, so
one middleware owns both, and its docstring says so.

## Configuration keys

All keys are read through the central accessor (`from config_manager import env`)
and mapped by each service's binding. Defaults make every key optional.

| Key | Default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Root level (`agent-service` defaults to `WARNING` via its own getter) |
| `LOG_FORMAT` | `text` | `text` or `json`, case-insensitive |
| `LOG_OUTPUT` | `console` | `console`, `file`, `syslog`, or `external` |
| `LOG_FILE_PATH` | `/var/log/agent-service/app.log` | File destination path |
| `LOG_MAX_SIZE` | `10485760` | Rotation threshold in bytes |
| `LOG_BACKUP_COUNT` | `5` | Rotated files kept |
| `LOG_INCLUDE_SOURCE` | `true` | Whether records carry module, function, and line |
| `LOG_QUIET_LOGGERS` | *(empty)* | Extra loggers pinned to WARNING, comma-separated |
| `LOG_SYSLOG_ADDRESS` | `localhost:514` | Syslog `host:port` |
| `LOG_SYSLOG_FACILITY` | `user` | Syslog facility |
| `LOG_EXTERNAL_URL` | *(unset)* | Log platform ingest URL; unset means no platform |
| `LOG_EXTERNAL_BEARER_TOKEN` | *(unset)* | Platform credential, sent as a bearer header |
| `LOG_EXTERNAL_BATCH_SIZE` | `100` | Records per platform call |
| `LOG_EXTERNAL_FLUSH_INTERVAL` | `5.0` | Seconds a partial batch waits |
| `LOG_EXTERNAL_MAX_QUEUE` | `1000` | Records held before the oldest is dropped |
| `LOG_EXTERNAL_MAX_RETRIES` | `3` | Attempts per batch before it is counted as lost |
| `LOG_EXTERNAL_RETRY_BACKOFF` | `0.5` | Seconds before the first retry; doubles per attempt |
| `LOG_EXTERNAL_SHUTDOWN_TIMEOUT` | `10.0` | Seconds the process waits for a final flush |
| `LOG_ELASTICSEARCH_INDEX` | *(unset)* | Fixed Elasticsearch index; unset means one index per service |

## Metrics catalog

Metrics are exposed on each service's `/metrics` endpoint in Prometheus format
and, when `OTEL_METRICS_ENABLED=true`, pushed to the collector as OTLP meters.
The two surfaces share the same names, so a dashboard works against either.

### Shipped today

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `http_requests_total` | counter | `service`, `method`, `route`, `status` | Every HTTP response, including the 503s the idempotency middleware short-circuits |
| `http_request_duration_seconds` | histogram | `service`, `method`, `route` | Request latency distribution |
| `http_request_errors_total` | counter | `service`, `method`, `route`, `status` | Responses with status >= 500 |
| `idempotency_decisions_total` | counter | `service`, `decision` | Replay/lock outcomes of the idempotency middleware |
| `idempotency_lock_wait_seconds` | histogram | `service` | Time spent waiting for an idempotency lock |

The first four are the governance contract (`OBS-001..004`); the idempotency
pair is `OBS-005..006`. Labels are bounded by design - `route` is the matched
route template, never the raw path, so cardinality cannot explode.

### Recommended next, by value

1. **Dependency health gauges** - `dependency_up{service, dependency}` and
   `dependency_degraded{service, dependency}` from the `DependencyRegistry` the
   services already fill at startup and on readiness checks. This turns the
   readiness endpoint into a time series: an operator sees a dependency flap in
   a graph instead of noticing a 503.
2. **Outbound dependency metrics** - `outbound_requests_total{service,
   dependency, outcome}` and `outbound_request_duration_seconds{service,
   dependency}` from agent-service's shared transport, plus
   `circuit_breaker_state{service, dependency}` (0 closed / 1 half-open /
   2 open). A dependency outage is then visible before it becomes a user-facing
   error.
3. **Process and runtime metrics** - the standard `prometheus_client` process
   and Python collectors (CPU, RSS, GC, open file descriptors, event-loop
   lag). Free to enable, and the first thing that answers "is the container
   itself healthy".
4. **Domain metrics, one per service** - agent: LLM call duration and token
   usage per provider; rag: ingestion duration, chunk counts, search latency;
   user: login outcomes and token validation failures; tools: tool invocations
   by name and connector call outcomes. These are the metrics product questions
   are asked from, and each is a small counter or histogram at an existing
   call site.

### Rules for adding metrics

- Bounded labels only: route templates, dependency names, outcome enums. Never
  a user id, a document id, or a raw path - one high-cardinality label can
  take a Prometheus down.
- Declare the metric in `packages/metrics`, not at the call site, so the
  governance contract can see it and the name exists even before its first
  increment.
- Every new metric gets a governance `OBS-` entry, so a service that stops
  exposing it fails the contract rather than silently disappearing from
  dashboards.

## Dependency policy

Dependencies use three policy classes.

| Policy | Meaning | Startup behavior | Readiness behavior |
| --- | --- | --- | --- |
| `required` | Core service capability can't work safely without it. | Retry, then fail startup. | `ready=false` |
| `degraded` | Service can start, but named features are disabled. | Retry, log degraded state, continue. | `ready=true`, `degraded=true` |
| `optional` | Diagnostics, telemetry, or non-core integrations. | Try once or retry lightly, then continue. | Informational |

Initial classification:

| Service | Required | Degraded | Optional |
| --- | --- | --- | --- |
| `user-service` | Postgres, Keycloak, Redis when idempotency is required | External Keycloak identity provider sync | LDAP when disabled by config |
| `agent-service` | Postgres, LangGraph checkpointer/store, Redis when idempotency is required | tools-service, rag-service, MinIO, Milvus, Ollama | Langfuse |
| `rag-service` | Postgres, Redis when idempotency is required | Neo4j, Milvus, embeddings, user-service authorization checks | none initially |
| `tools-service` | Required environment configuration, Postgres when DB-backed tools are used, Redis when idempotency is required | user-service authorization checks, RAG service for knowledge tools | external web targets used by individual tools |

The idempotency contract stays intact. Optional idempotency modes fail open
when Redis is unavailable; required modes return `503` for affected requests.

Required dependencies fail startup only when the service can't provide its core
contract without them. Degraded dependencies don't fail startup, but their
feature handlers must fail clearly when invoked. Optional dependencies are
reported only when they are configured or actively used.

## Retry policy

Startup retry is bounded and explicit. It must not hide permanent
configuration errors.

Default values:

- `STARTUP_RETRY_ATTEMPTS=5`
- `STARTUP_RETRY_INITIAL_DELAY_SECONDS=0.5`
- `STARTUP_RETRY_MAX_DELAY_SECONDS=8.0`
- `STARTUP_RETRY_JITTER=true`
- `STARTUP_CONNECT_TIMEOUT_SECONDS=5.0`

Retryable failures:

- Connection refused.
- DNS lookup failure.
- Connection timeout.
- Read timeout during readiness or health check.
- HTTP `502`, `503`, or `504` from internal dependencies.

Non-retryable failures:

- Missing required environment variables.
- Invalid URL or invalid port.
- Authentication failures such as HTTP `401` or `403`.
- Authorization failures from Keycloak admin APIs.
- Migration conflicts that require human action.

Each retry attempt logs one compact warning. The final failure logs one
structured error with a remediation hint.

## Readiness and health

Health endpoints keep their current lightweight liveness behavior. Readiness
endpoints expose dependency state from the `dependency_registry`.

| Service | Liveness | Readiness |
| --- | --- | --- |
| `agent-service` | `GET /api/v1/health` | `GET /api/v1/health/ready` |
| `user-service` | `GET /api/v1/health/` | `GET /api/v1/health/ready` |
| `rag-service` | `GET /api/v1/health` | `GET /api/v1/health/ready` |
| `tools-service` | `GET /health` | `GET /health/ready` |

Readiness response:

```json
{
  "status": "ready",
  "service": "agent-service",
  "dependencies": {
    "postgres": {"status": "ok", "required": true},
    "redis": {"status": "degraded", "required": false},
    "rag-service": {"status": "degraded", "required": false}
  }
}
```

If a required dependency fails, readiness returns `503` with
`"status": "not_ready"`. If only degraded or optional dependencies fail,
readiness returns `200` with the degraded details. `user-service` refreshes its
Postgres state with a live `SELECT 1` on each readiness call; the other
services report the startup state recorded in the registry.

## Service boundary rules

- `user-service` owns identity, user profiles, roles, permissions, and Keycloak
  administrative lifecycle.
- Other backend services don't create Keycloak users, roles, clients, realms,
  or identity providers.
- Other services can validate tokens locally through a thin adapter because
  token validation is an edge concern.
- Permission checks and user lookup remain behind `user-service` APIs.
- Runtime business logic must depend on service-local ports or clients, not raw
  `httpx` calls scattered through use cases.
- Startup checks don't call feature endpoints that cause side effects.
- A service must not fail startup because a degraded dependency for an unused
  feature is unavailable.

The architecture gate (`scripts/quality/check_architecture.py`) enforces the
Keycloak boundary: Keycloak admin API usage (`/admin/realms/` or a
`KeycloakAdmin` client) outside `user-service` is a HARD finding, with an
exemption for documented compatibility shims that carry a removal note.
