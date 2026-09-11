# Backend Observability Contract

All backend services (`agent-service`, `user-service`, `rag-service`,
`tools-service`) share one observability contract for startup logging,
dependency state, retry behavior, and readiness. Each service keeps a local
observability module with the same public API:

- `configure_logging(settings)` — configure root and service loggers once.
- `get_logger(name)` — return a standard logger.
- `DependencyPolicy`, `DependencyStatus`, `DependencyRegistry` — dependency
  state tracking with a module-level `dependency_registry` singleton.
- `readiness_payload(service_name=...)` — build the readiness response body.
- `retry_async()` / `retry_sync()` — bounded startup retries.
- `format_exception()` / `dependency_error_fields()` — safe structured log
  fields for exceptions.

The modules are service-local because the repository does not yet expose a
shared Python package. They share the same API and tests; a later cleanup can
extract a shared internal package if one is added.

New startup, readiness, and dependency-handling code must import loggers from
the service-local observability module. Existing modules that still call
`logging.getLogger(...)` continue to receive the centralized root formatter,
but they are tracked for migration to the stricter single-module import rule.

## Logging contract

Every backend service uses the same log field contract. Human-readable text is
the default for local development; JSON is available for containerized
environments. Text logs colorize severity and dependency status values with
ANSI colors for local terminal readability. JSON logs never include ANSI color
codes.

Required fields:

- `timestamp`
- `level`
- `service`
- `logger`
- `event`
- `message`
- `request_id`
- `dependency`
- `operation`
- `attempt`
- `max_attempts`
- `elapsed_ms`
- `status`

Exception fields must be safe:

- `exception_type`
- `exception_message`
- `retryable`
- `hint`

Logs must not include database passwords, bearer tokens, API keys, connection
URLs with credentials, or unbounded stack traces in normal startup failure
messages. Full stack traces are reserved for debug logs or final fatal startup
failures.

Example text log:

```text
2026-09-01T11:20:42.118Z INFO service=user-service
  event=startup.dependency.ok dependency=postgres operation=migrate
  attempt=2/5 elapsed_ms=432 status=ok
  message="Postgres migrations completed."
```

Example JSON log:

```json
{
  "timestamp": "2026-09-01T11:20:42.118Z",
  "level": "INFO",
  "service": "user-service",
  "event": "startup.dependency.ok",
  "dependency": "postgres",
  "operation": "migrate",
  "attempt": 2,
  "max_attempts": 5,
  "elapsed_ms": 432,
  "message": "Postgres migrations completed."
}
```

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
| `user-service` | Postgres, Keycloak when `KEYCLOAK_ENABLED=true` and bootstrap is required, Redis when idempotency is required | External Keycloak identity provider sync | LDAP when disabled by config |
| `agent-service` | Postgres when `DATABASE_TYPE=postgres`, LangGraph checkpointer/store, Redis when idempotency is required | tools-service, rag-service, MinIO, Airbyte, Milvus, Ollama | Langfuse |
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
