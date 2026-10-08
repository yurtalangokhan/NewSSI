# Environment Variables

## Gateway authentication and organization orchestration

The Gateway implementation reads the following settings from infrastructure
configuration. Keep secrets in your local environment or secret manager.

| Variable | Purpose |
| --- | --- |
| `GATEWAY_URL` | Gateway base URL used by web auth and user-service catalog composition. Compose supplies the container URL. |
| `GATEWAY_KEYCLOAK_CLIENT_ID` | Dedicated confidential introspection client (`gateway-client`), independent of the gateway implementation. |
| `GATEWAY_KEYCLOAK_CLIENT_SECRET` | Required secret for that client, shared only by bootstrap and Gateway. |
| `GATEWAY_ALLOWED_REDIRECT_URIS` | Required JSON array of exact browser callback URLs; wildcards are rejected. |
| `GATEWAY_COOKIE_SECURE` | Set explicitly to `true`; use `false` only for local HTTP browser testing. |
| `GATEWAY_EXTERNAL_IDP_ALIAS` | Optional override for the external Keycloak identity-provider alias. When empty, Gateway uses `EXTERNAL_KEYCLOAK_ALIAS` if `EXTERNAL_KEYCLOAK` is enabled. |
| `EXTERNAL_KEYCLOAK`, `EXTERNAL_KEYCLOAK_ALIAS` | Enable external login and select its broker alias (default `external-keycloak`). Compose passes these settings to APISIX so the external login page and broker password login match the configured provider. |
| `GATEWAY_BROKER_URL_REWRITES` | Optional JSON object mapping a public Keycloak/IdP URL prefix to a prefix the gateway container can reach, e.g. `{"https://sso.example.com":"http://idp:8080"}`. |
| `GATEWAY_REDIS_DB` | Redis database for one-time OIDC transactions; set explicitly, typically `0`. |
| `KEYCLOAK_ISSUER_URL` | Exact public realm issuer used for token validation and browser redirects. |
| `KEYCLOAK_BASE_URL` | Keycloak server URL reached directly by Gateway and bootstrap. |
| `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Existing login client and its secret, when confidential. |
| `KEYCLOAK_REALM` | Required realm name used by Keycloak clients and authorization operations. |
| `KEYCLOAK_USER_SERVICE_CLIENT_ID`, `KEYCLOAK_AGENT_SERVICE_CLIENT_ID`, `KEYCLOAK_RAG_SERVICE_CLIENT_ID`, `KEYCLOAK_TOOLS_SERVICE_CLIENT_ID` | Required client IDs for service role discovery and authorization resources. |
| `INTERNAL_SERVICE_TOKEN` | Required existing machine-call credential; Gateway now verifies it too. |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` | Redis connection used for OIDC state and serialized policy writes. |
| `REDIS_HOST_CONTAINER` | Redis hostname passed to APISIX as `REDIS_HOST`; use `redis` for the Compose service. |
| `REDIS_CONTAINER_HOST` | Redis host as reached from inside application containers. Compose passes it as `REDIS_HOST`; host-run processes use the separate `REDIS_HOST` value. |
| `APP_IMAGE_TAG` | Built APISIX image tag, supplied explicitly by the environment. |

The APISIX Compose service has no environment interpolation fallbacks. Set its
image tags, HTTP port, and Gateway settings in `configs/.env`. Optional
`GATEWAY_EXTERNAL_IDP_ALIAS`, `GATEWAY_BROKER_URL_REWRITES`, and `REDIS_PASSWORD`
can be empty. Secret and callback URL checks still reject missing required values.

To disable external login, disable `EXTERNAL_KEYCLOAK` and leave
`GATEWAY_EXTERNAL_IDP_ALIAS` empty. Recreate APISIX after changing these
environment settings so its generated login metadata reflects the new values.

Keep the internal credential consistent across Gateway and application services.
Configure the four `*_SERVICE_UPSTREAM_ADDR` values explicitly for Gateway's
backend destinations. Application service URLs in both Compose modes point to
Gateway. Configuration rendering requires these destinations and does not fall
back to hardcoded backend ports.

For example, the redirect setting for local HTTP development can contain
`["http://localhost:8126/auth/oidc/callback"]`; use your actual browser origin.
The same callback must be registered on the Keycloak login client.

Provide the dedicated Gateway secret and the exact
`GATEWAY_ALLOWED_REDIRECT_URIS` callback array in `configs/.env` before
`make env-check` or stack startup. Example upstream address defaults target
local host-run backends; for container-only production, configure reachable
container destinations and the service ports from your environment.

Backend services share `configs/.env`. The shared `env` package (`packages/config-manager`) loads
that file once before settings are constructed. Existing process variables take
precedence, and loading does not depend on the working directory. Backend
startup no longer searches `apps/*/.env` files.

| Service | Configuration entrypoint | Database key prefix |
| --- | --- | --- |
| Agent | `core/config/settings.py` | `POSTGRES_AGENT_SERVICE_` |
| User | `src/config.py` | `POSTGRES_USER_SERVICE_` |
| RAG | `config_manager` | `POSTGRES_RAG_SERVICE_` |
| Tools | `src/core/settings.py` | `POSTGRES_TOOL_SERVICE_` |

Only `load_environment()` loads the shared file. Application code consumes
typed service settings, which retain type conversion and validation. Database prefixes
have `USER`, `PASSWORD`, and `DB` suffixes; shared connection keys are
`POSTGRES_HOST` and `POSTGRES_PORT`. Infrastructure credentials use
`POSTGRES_ADMIN_USER` and `POSTGRES_ADMIN_PASSWORD`.

The config_manager catalog separates internal service URLs from web
runtime URLs. Set the following keys for internal calls:

| Variable | Gateway path |
| --- | --- |
| `INTERNAL_TOOLS_SERVICE_URL` | `/internal/tools-service/mcp` |
| `INTERNAL_RAG_SERVICE_API_URL` | `/internal/rag-service` |
| `INTERNAL_USER_SERVICE_URL` | `/internal/user-service` |
| `INTERNAL_AGENT_SERVICE_URL` | `/internal/agent-service/api/v1` |

`INTERNAL_SERVICE_TOKEN` remains the shared internal authentication key. Web
runtime uses separate `AGENT_SERVICE_URL`, `USER_SERVICE_URL`, and
`RAG_SERVICE_URL` keys. Service settings read each key independently and retains
existing unprefixed properties for web and public metadata. Backend clients
read only the internal keys, with no fallback to web URLs or direct service
ports. Set required internal URLs before startup. The catalog also records the
web runtime's `AUTH_TYPE`.

`AUTHENTICATION_SECRET` no longer signs or verifies user tokens: Keycloak and
Gateway own them. With Keycloak disabled, user-service authenticates nothing: a
request carrying any token is treated as the development user, and so is a
token-less request while this secret is unset. Encrypted application
credentials do not share a key: see [Encryption keys](#encryption-keys) below.
`AGENT_SERVICE_PORT`, `USER_SERVICE_PORT`, and `TOOLS_SERVICE_PORT` feed the
corresponding typed settings. Service-specific Keycloak values use
`KEYCLOAK_<AGENT|USER|RAG|TOOL>_SERVICE_CLIENT_ID`, `CLIENT_SECRET`, and `AUDIENCE`.
Generic Keycloak names remain fallback aliases where previously supported.

For a mounted file or an isolated test, set `AGENTICAI_ENV_FILE` to an explicit
file path. An explicit missing file fails startup. Without this override,
environment-only containers can run without a local file. Repeated loads do not
restore secrets already removed from the process environment.

Install the shared package with `uv sync --frozen` in each service directory.
The frontend continues to use its existing Next.js environment loading.

## Infrastructure (`configs/.env`)

The keys of the `configs` section of the central catalog (`packages/config-manager/src/config_manager/manager.py`), in catalog order. `generated` marks a credential `make env-init` creates; `POSTGRES_ADMIN_USER` / `POSTGRES_ADMIN_PASSWORD` are the superuser of the infrastructure PostgreSQL, the per-service `POSTGRES_<AGENT|USER|RAG|TOOL>_SERVICE_{USER,PASSWORD,DB}` keys are listed with their services below. The `*_BIND_ADDR` keys choose the host interface of a published port (`127.0.0.1` exposes nothing; a shared server sets `0.0.0.0` or its interface address for the services it means to expose).

The `LOG_*` and `OTEL_*` keys are shared by every backend service through `packages/observability`; `docs/observability.md` holds the full contract (including `LOG_FILE_PATH`, which the services read but the catalog does not declare). All of them are optional: tracing and OTLP metrics stay off until `OTEL_ENABLED` is set. The observability stack keys (`ELASTIC*`, `KIBANA_*`, `GRAFANA_*`, `LOG_RETENTION_DAYS`) configure the compose services that store and render telemetry; their host ports are loopback-only.

| Variable | Description | Default |
| --- | --- | --- |
| `POSTGRES_HOST` | Postgres host address for local app services. | `localhost` |
| `POSTGRES_PORT` | Host port mapped to infrastructure Postgres. | `8124` |
| `POSTGRES_BIND_ADDR` | Postgres bind address for the published port. | `127.0.0.1` |
| `POSTGRES_ADMIN_USER` | Infrastructure Postgres superuser. | `postgres` |
| `POSTGRES_ADMIN_PASSWORD` | Infrastructure Postgres password. | generated |
| `OLLAMA_IMAGE_TAG` | Ollama Docker image tag. | `latest` |
| `OLLAMA_PORT` | Host port mapped to built-in Ollama. | `11434` |
| `OLLAMA_BIND_ADDR` | Ollama bind address for the published port. | `127.0.0.1` |
| `OLLAMA_PRELOAD_MODELS` | Space-separated Ollama models pulled by scripts/pull_ollama_models.sh. | `llama3.1:8b nomic-embed-text` |
| `LOG_LEVEL` | Shared log level for services. | `INFO` |
| `LOG_FORMAT` | Shared log format for services (text or JSON). | `JSON` |
| `LOG_OUTPUT` | Log destination: console, file, syslog, or elasticsearch. | `console` |
| `LOG_INCLUDE_SOURCE` | Whether log records carry module, function, and line. | `true` |
| `LOG_QUIET_LOGGERS` | Extra loggers pinned to WARNING, comma-separated. | _(empty)_ |
| `LOG_SYSLOG_ADDRESS` | Syslog host:port for the syslog destination. | `localhost:514` |
| `LOG_SYSLOG_FACILITY` | Syslog facility for the syslog destination. | `user` |
| `LOG_ELASTICSEARCH_INDEX` | Fixed Elasticsearch log index; empty means one index per service. | _(empty)_ |
| `LOG_EXTERNAL_URL` | Log platform ingest URL for the elasticsearch destination. | _(empty)_ |
| `LOG_EXTERNAL_BEARER_TOKEN` | Bearer credential for the log platform. | _(empty)_ |
| `LOG_EXTERNAL_BATCH_SIZE` | Records delivered per log platform call. | `100` |
| `LOG_EXTERNAL_FLUSH_INTERVAL` | Seconds a partial log batch waits before delivery. | `5.0` |
| `LOG_EXTERNAL_MAX_QUEUE` | Records held before the oldest log record is dropped. | `1000` |
| `LOG_EXTERNAL_MAX_RETRIES` | Delivery attempts per log batch before it is counted as lost. | `3` |
| `LOG_EXTERNAL_RETRY_BACKOFF` | Seconds before the first log delivery retry; doubles per attempt. | `0.5` |
| `LOG_EXTERNAL_SHUTDOWN_TIMEOUT` | Seconds the process waits for a final log flush. | `10.0` |
| `OTEL_ENABLED` | Whether services produce OpenTelemetry traces and OTLP metrics. | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP/http endpoint of the telemetry collector. | `http://otel-collector:4318` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Collector credentials as Key=Value pairs, comma-separated. | _(empty)_ |
| `OTEL_TRACES_SAMPLE_RATIO` | Fraction of requests traced, 0.0 to 1.0. | `1.0` |
| `OTEL_METRICS_ENABLED` | Whether OTLP metrics are exported alongside traces. | `false` |
| `OTEL_METRICS_EXPORT_INTERVAL` | Milliseconds between OTLP metric exports. | `60000` |
| `ELASTIC_VERSION` | Elasticsearch and Kibana image tag. | `8.15.2` |
| `ELASTICSEARCH_PORT` | Host port mapped to Elasticsearch. | `9200` |
| `ES_JAVA_OPTS` | Elasticsearch JVM heap settings. | `-Xms512m -Xmx512m` |
| `KIBANA_PORT` | Host port mapped to Kibana. | `5601` |
| `PROMETHEUS_VERSION` | Prometheus image tag. | `v2.54.1` |
| `PROMETHEUS_PORT` | Host port mapped to Prometheus. | `9090` |
| `GRAFANA_VERSION` | Grafana image tag. | `11.1.0` |
| `GRAFANA_PORT` | Host port mapped to Grafana. | `3001` |
| `GRAFANA_ADMIN_USER` | Grafana admin username for the development stack. | `admin` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password for the development stack. | generated |
| `LOG_RETENTION_DAYS` | Days Elasticsearch keeps logs and traces before deleting them. | `30` |
| `NEO4J_URI` | Neo4j Bolt URI for app services. | `bolt://localhost:8697` |
| `NEO4J_BIND_ADDR` | Neo4j bind address for the published ports. | `127.0.0.1` |
| `NEO4J_USERNAME` | Neo4j username. | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password. | generated |
| `NEO4J_PLUGINS` | Neo4j plugin list. | `["apoc"]` |
| `NEO4J_HEAP_INITIAL_SIZE` | Neo4j initial heap size. | `512m` |
| `NEO4J_HEAP_MAX_SIZE` | Neo4j max heap size. | `1g` |
| `NEO4J_PAGECACHE_SIZE` | Neo4j page cache size. | `512m` |
| `NEO4J_PROCEDURES_UNRESTRICTED` | Neo4j unrestricted procedures. | `apoc.*` |
| `NEO4J_PROCEDURES_ALLOWLIST` | Neo4j allowed procedures. | `apoc.*` |
| `KEYCLOAK_BASE_URL` | Keycloak public base URL. | `http://localhost:8085` |
| `KEYCLOAK_REALM` | Keycloak realm. | `agenticai-v1` |
| `KEYCLOAK_ISSUER_URL` | Keycloak issuer URL used by APISIX JWT validation. | `http://localhost:8085/realms/agenticai-v1` |
| `KEYCLOAK_CLIENT_ID` | Frontend Keycloak client id bootstrapped by infra. | `web-client` |
| `KEYCLOAK_CLIENT_SECRET` | Frontend Keycloak client secret; empty means public client. | _(empty)_ |
| `KEYCLOAK_REDIRECT_URI` | Primary frontend OIDC callback URI. | `http://localhost:3000/auth/oidc/callback` |
| `KEYCLOAK_REDIRECT_URIS` | Allowed frontend OIDC callback URIs. | `http://localhost:3000/auth/oidc/callback,http://localhost:3000/*` |
| `KEYCLOAK_POST_LOGOUT_REDIRECT_URIS` | Allowed post logout redirect URIs. | `+` |
| `KEYCLOAK_DB_VENDOR` | Keycloak database vendor. | `postgres` |
| `KEYCLOAK_DB_HOST` | Keycloak database host inside Docker. | `postgres` |
| `KEYCLOAK_DB_NAME` | Keycloak database name. | `keycloak` |
| `KEYCLOAK_ADMIN` | Keycloak bootstrap admin user. | `admin` |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak bootstrap admin password. | generated |
| `KEYCLOAK_HEALTH_ENABLED` | Enable Keycloak health endpoints. | `true` |
| `KEYCLOAK_HOSTNAME_STRICT` | Disable strict hostname checks in development. | `false` |
| `KEYCLOAK_WEB_ORIGIN` | Primary frontend web origin. | `http://localhost:3000` |
| `KEYCLOAK_WEB_ORIGINS` | Allowed frontend web origins. | `http://localhost:3000` |
| `KEYCLOAK_TEST_USER` | Bootstrap test username. | `test-user` |
| `KEYCLOAK_TEST_EMAIL` | Bootstrap test user email. | `test-user@example.com` |
| `KEYCLOAK_TEST_PASSWORD` | Bootstrap test user password. | generated |
| `KEYCLOAK_DEFAULT_ADMIN_USER` | Bootstrap app admin username. | `admin` |
| `KEYCLOAK_DEFAULT_ADMIN_EMAIL` | Bootstrap app admin email. | `admin@example.com` |
| `KEYCLOAK_DEFAULT_ADMIN_PASSWORD` | Bootstrap app admin password. | generated |
| `KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME` | Bootstrap app admin first name. | `Admin` |
| `KEYCLOAK_DEFAULT_ADMIN_LAST_NAME` | Bootstrap app admin last name. | `User` |
| `KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE` | Bootstrap app admin realm role. | `admin` |
| `KEYCLOAK_PUBLIC_HOSTNAME` | Public hostname advertised by Keycloak. | `localhost` |
| `KEYCLOAK_PUBLIC_PORT` | Public port advertised by Keycloak. | `8085` |
| `KEYCLOAK_BIND_ADDR` | Keycloak bind address for the published port; browsers of remote developers need it widened or a proxy in front. | `127.0.0.1` |
| `APP_IMAGE_TAG` | Built application container image tag. | `latest` |
| `REDIS_HOST_CONTAINER` | Redis host reached by the APISIX container. | `redis` |
| `APISIX_IMAGE_TAG` | APISIX container image version. | `3.18.0-debian` |
| `APISIX_HTTP_PORT` | APISIX public HTTP port. | `8000` |
| `GATEWAY_KEYCLOAK_CLIENT_ID` | Gateway Keycloak client. | `gateway-client` |
| `GATEWAY_KEYCLOAK_CLIENT_SECRET` | Gateway Keycloak client secret. | generated |
| `USER_SERVICE_UPSTREAM_ADDR` | APISIX user-service upstream host:port. | `host.docker.internal:8090` |
| `AGENT_SERVICE_UPSTREAM_ADDR` | APISIX agent-service upstream host:port. | `host.docker.internal:8123` |
| `RAG_SERVICE_UPSTREAM_ADDR` | APISIX RAG upstream host:port. | `host.docker.internal:8083` |
| `TOOLS_SERVICE_UPSTREAM_ADDR` | APISIX tools upstream host:port. | `host.docker.internal:8003` |
| `VECTOR_DB_PROVIDER` | Vector database provider used by app services. | `milvus` |
| `MILVUS_HOST` | Milvus host address for app services. | `localhost` |
| `MILVUS_PORT` | Milvus host port. | `9765` |
| `MILVUS_USER` | Milvus username; empty when auth is disabled. | _(empty)_ |
| `MILVUS_PASSWORD` | Milvus password; empty when auth is disabled. | _(empty)_ |
| `MILVUS_BIND_ADDR` | Milvus bind address for published ports. | `127.0.0.1` |
| `MINIO_BIND_ADDR` | MinIO bind address for the published ports. | `127.0.0.1` |
| `MILVUS_ETCD_ENDPOINTS` | Milvus etcd endpoints. | `etcd:2379` |
| `MILVUS_MINIO_ADDRESS` | Milvus MinIO address. | `minio:9000` |
| `MILVUS_ETCD_AUTO_COMPACTION_MODE` | Milvus etcd compaction mode. | `revision` |
| `MILVUS_ETCD_AUTO_COMPACTION_RETENTION` | Milvus etcd compaction retention. | `1000` |
| `MILVUS_ETCD_QUOTA_BACKEND_BYTES` | Milvus etcd quota bytes. | `4294967296` |
| `MILVUS_ETCD_SNAPSHOT_COUNT` | Milvus etcd snapshot count. | `50000` |
| `MINIO_ROOT_USER` | MinIO root username for Milvus object storage. | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | MinIO root password for Milvus object storage. | generated |
| `REDIS_HOST` | Redis host for idempotency middleware. | `localhost` |
| `REDIS_CONTAINER_HOST` | Redis host as reached from inside Docker containers (the compose service name); REDIS_HOST is the host-side address. | `redis` |
| `REDIS_PORT` | Redis port for idempotency middleware. | `6379` |
| `REDIS_BIND_ADDR` | Redis bind address for the published port. | `127.0.0.1` |
| `REDIS_DB` | Redis database index for idempotency middleware. | `0` |
| `REDIS_PASSWORD` | Redis password for idempotency middleware. | generated |

---

## Saved connector runtime

Connector configurations are stored per user in user-service, encrypted under
`CONNECTOR_CONFIG_ENCRYPTION_KEY`. agent-service keeps only a reference and
reads the decrypted configuration through user-service's internal API when a
sync or a live connector tool needs it. Do not place source credentials in an
agent definition or in chat arguments.

| Service | Variable | Purpose |
| --- | --- | --- |
| tools-service | `INTERNAL_AGENT_SERVICE_URL` | Agent-service internal gateway base, ending in `/api/v1` |
| agent-service | `INTERNAL_USER_SERVICE_URL` | User-service internal gateway base that serves stored connector configurations |
| all three services | `INTERNAL_SERVICE_TOKEN` | Authenticate internal connector resolution and configuration reads |
| user-service | `CONNECTOR_CONFIG_ENCRYPTION_KEY` | Fernet key sealing `user_connector_configs.config_encrypted` |

## APISIX (`configs/.env`)

APISIX runs in standalone YAML mode. It does not use a gateway database.
The custom image includes the Keycloak authentication plugin.

| Variable | Description | Default |
| --- | --- | --- |
| `APISIX_IMAGE_TAG` | Base APISIX image version | `3.18.0-debian` |
| `APISIX_HTTP_PORT` | Published gateway HTTP port | `8000` |
| `GATEWAY_KEYCLOAK_CLIENT_ID` | Confidential Keycloak client | `gateway-client` |
| `GATEWAY_KEYCLOAK_CLIENT_SECRET` | Client secret shared with bootstrap | Generated |
| `*_SERVICE_UPSTREAM_ADDR` | Backend `host:port`, without a URL scheme | Local host destinations |


---

## User Service (`configs/.env`)

| Variable                      | Description                             | Default                                                       |
| ----------------------------- | --------------------------------------- | ------------------------------------------------------------- |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER_SERVICE_USER` / `POSTGRES_USER_SERVICE_PASSWORD` / `POSTGRES_USER_SERVICE_DB` | PostgreSQL connection parts (the service assembles the DSN itself; its bootstrap creates the role and the database) | `localhost` / `8124` / `postgres` / generated / `user_service` |
| `KEYCLOAK_SERVER_URL`         | Keycloak base URL                       | `http://localhost:8080`                                       |
| `KEYCLOAK_REALM`              | Keycloak realm name                     | `agenticai-v1`                                                |
| `KEYCLOAK_USER_SERVICE_CLIENT_ID`          | Keycloak client ID                      | `user-service-client`                                         |
| `KEYCLOAK_USER_SERVICE_CLIENT_SECRET`      | Keycloak client secret                  | —                                                             |
| `USER_API_KEY_ENCRYPTION_KEY` | **Required.** Fernet key for stored API key hashes. | — |
| `SYSTEM_SETTINGS_ENCRYPTION_KEY` | **Required.** Fernet key for secrets inside persisted system settings. | — |
| `CONNECTOR_CONFIG_ENCRYPTION_KEY` | **Required.** Fernet key for stored per-user connector configurations. | — |
| `DAG_AUTH_ENABLED`            | Enable DAG auth broker                  | `false`                                                       |
| `DAG_AUTH_JWT_SECRET`         | Secret for DAG-signed tokens            | —                                                             |
| `EXTERNAL_AUTH_BROKER_URL`    | External auth broker URL                | —                                                             |
| `EXTERNAL_AUTH_BROKER_TOKEN`  | External auth broker API token          | —                                                             |
| `INTERNAL_SERVICE_TOKEN`      | Secret for service-to-service auth      | —                                                             |
| `LOG_LEVEL`                   | Python logging level                    | `INFO`                                                        |
| `SERVICE_NAME`                | Service identifier                      | `user-service`                                                |
| `CORS_ORIGINS`                | Allowed CORS origins                    | `*`                                                           |
| `HOST`                        | Server bind address                     | `0.0.0.0`                                                     |
| `SERVICE_PORT`                | Server port                             | `8090`                                                        |
| `REDIS_HOST`                  | Redis host for idempotency cache        | `localhost`                                                   |
| `REDIS_PORT`                  | Redis port for idempotency cache        | `6379`                                                        |
| `REDIS_DB`                    | Redis DB for idempotency cache          | `0`                                                           |
| `REDIS_PASSWORD`              | Redis password for idempotency cache    | —                                                             |
| `IDEMPOTENCY_TTL`             | Cached response and key-owner TTL       | `86400`                                                       |
| `IDEMPOTENCY_ENABLED`         | Enable shared idempotency middleware    | `true`                                                        |
| `IDEMPOTENCY_ENFORCE_REQUIRED_KEYS` | Require keys for `required_replay` routes | `true`                                                   |
| `IDEMPOTENCY_LOCK_TTL`        | Redis lock TTL for in-flight requests   | `10`                                                          |
| `IDEMPOTENCY_WAIT_TIMEOUT`    | Wait time for an in-flight cached replay | `10.0`                                                       |

---

## Agent Service (`configs/.env`)

| Variable                 | Description                                                                              | Default                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_AGENT_SERVICE_USER` / `POSTGRES_AGENT_SERVICE_PASSWORD` / `POSTGRES_AGENT_SERVICE_DB` | PostgreSQL connection parts (the service assembles the DSN itself; its bootstrap creates the role and the database) | `localhost` / `8124` / `postgres` / generated / `agent_service` |
| `POSTGRES_POOL_SIZE`     | Connections the SQLAlchemy pool **retains** for the service's own tables. Too small and every concurrent burst opens and closes a fresh connection: SQLAlchemy closes overflow connections as soon as they are returned. | `10` |
| `POSTGRES_MAX_OVERFLOW`  | Disposable extras allowed above `POSTGRES_POOL_SIZE` before callers queue                            | `5`                                                           |
| `POSTGRES_POOL_TIMEOUT_SECONDS` | How long a caller waits for a free connection before it errors                                | `30`                                                          |
| `POSTGRES_POOL_RECYCLE_SECONDS` | Age after which a pooled connection is recycled                                             | `1800`                                                        |
| `POSTGRES_POOL_USE_LIFO` | Reuse the hottest connection and let idle ones age out                                               | `true`                                                        |
| `POSTGRES_COMMAND_TIMEOUT_SECONDS` | Server-side statement timeout for a single query on a pooled connection                     | `30`                                                          |
| `POSTGRES_MIN_CONNECTIONS_PER_POOL` / `POSTGRES_MAX_CONNECTIONS_PER_POOL` | LangGraph checkpointer/store pool bounds. In `psycopg_pool` these are `min_size`/`max_size`, i.e. "keep between N and M" — **not** the same knobs as the SQLAlchemy pool above. | `2` / `20` |
| `INTERNAL_SERVICE_TOKEN` | Service-to-service auth token                                                            | —                                                             |
| `LLM_PROVIDER_API_ENCRYPTION_KEY` | **Required.** Fernet key for stored LLM provider API keys. | — |
| `MCP_CREDENTIAL_ENCRYPTION_KEY` | **Required.** Fernet key for stored external-MCP credentials and OAuth tokens. | — |
| `MCP_OAUTH_ENCRYPTION_KEY` | **Required.** Fernet key for stored MCP OAuth client secrets. | — |
| `MAIL_CONFIG_ENCRYPTION_KEY` | **Required.** Fernet key for stored SMTP passwords. | — |
| `MCP_OAUTH_REDIRECT_BASE` | Public origin used to build the external-MCP OAuth redirect URI (`{base}/mcp/oauth/callback`). Required, no fallback; must be https unless loopback | _(none — the flow refuses to start)_ |
| `MCP_EXTERNAL_ENABLED`   | Load tools from connected external MCP servers into agent runs                            | `true`                                                        |
| `MCP_OAUTH_HTTP_TIMEOUT` | Timeout (seconds) for MCP OAuth discovery / DCR / token requests                         | `30`                                                          |
| `INTERNAL_USER_SERVICE_URL` | Internal user-service gateway URL | — |
| `INTERNAL_RAG_SERVICE_API_URL` | Internal RAG base URL used by the flow compiler and option resolvers. | — |
| `RAG_HTTP_TIMEOUT_SECONDS` | Per-request timeout (seconds) for agent-service -> rag-service calls                   | `15`                                                          |
| `KEYCLOAK_SERVER_URL`    | Keycloak base URL                                                                        | `http://localhost:8080`                                       |
| `KEYCLOAK_REALM`         | Keycloak realm                                                                           | `agenticai-v1`                                                |
| `KEYCLOAK_AGENT_SERVICE_CLIENT_ID`     | Keycloak client ID for agent-service                                                     | —                                                             |
| `OPENAI_API_KEY`         | OpenAI API key (models: `gpt-4o`, `gpt-4o-mini`)                                         | —                                                             |
| `ANTHROPIC_API_KEY`      | Anthropic API key (models: `claude-sonnet-4`, `claude-haiku-3`)                          | —                                                             |
| `OLLAMA_BASE_URL`        | Ollama server URL                                                                        | `http://localhost:11434`                                      |
| `OLLAMA_DEFAULT_MODEL`   | Default Ollama model                                                                     | `llama3`                                                      |
| `FAKE_MODEL`             | Use mock LLM (no API key needed)                                                         | `false`                                                       |
| `PROXY_SERVICE_API_KEY`  | Proxy API key                                                                            | —                                                             |
| `SERVICE_NAME`           | Service identifier                                                                       | `agent-service`                                               |
| `LOG_LEVEL`              | Logging level                                                                            | `INFO`                                                        |
| `HOST`                   | Server bind address                                                                      | `0.0.0.0`                                                     |
| `PORT`                   | Server port                                                                              | `8080`                                                        |
| `MCP_PORT`               | MCP proxy port                                                                           | `8001`                                                        |
| `CONNECTOR_MAX_CONCURRENT_SYNCS` | Connector syncs that run at the same time; further syncs wait as pending jobs    | `1`                                                           |
| `CONNECTOR_SYNC_BATCH_SIZE` | Records per batch sent to rag-service during a sync                                   | `200`                                                         |
| `CONNECTOR_SYNC_TIMEOUT_SECONDS` | Fail a sync that runs longer than this many seconds; `0` turns the limit off     | `86400`                                                       |
| `CONNECTOR_SCHEDULER_POLL_SECONDS` | How often the sync scheduler looks for due schedules                           | `30`                                                          |
| `CONNECTORS_DISABLED`    | Comma-separated connector names hidden from the catalog and refused at sync time          | _(unset)_                                                     |
| `CONNECTORS_ENABLED`     | Comma-separated connector names to enable although hidden by default. `jsonl_file`, `file_upload`, and `file_server` read the service's own filesystem and stay hidden unless listed here | _(unset)_            |
| `DOCUMENT_TOOLS_ENABLED` | Always-on `create_document`/`create_spreadsheet` tools on every agent graph              | `true`                                                        |
| `MERMAID_RENDER_TIMEOUT_SECONDS` | Per-call timeout for rendering one Mermaid fence to PNG before the render pool is recycled | `10`                                                          |
| `MERMAID_RENDER_WORKERS` | Worker subprocesses in the Mermaid render pool (one `ThreadPoolExecutor` thread drives each), each keeping one warm engine | `1`                                                           |
| `MERMAID_MAX_SOURCE_CHARS` | Max characters accepted for one Mermaid fence's source before it is rejected as too large. The web client mirrors the default in `mermaidSource.ts` as a pre-check (a contract test keeps them equal); raising it here also needs that constant changed | `20000`                                                       |
| `DOCUMENT_DIAGRAM_CACHE_SIZE` | Entries in the rendered-diagram LRU cache, keyed by `renderer_version:sha256(source)` (server renders use the neutral theme) | `256`                                                         |
| `OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED` | Enable optional Chromium fallback for built-in web fetch failures          | `false`                                                       |
| `REDIS_HOST`             | Redis host for idempotency cache                                                         | `localhost`                                                   |
| `REDIS_PORT`             | Redis port for idempotency cache                                                         | `6379`                                                        |
| `REDIS_DB`               | Redis DB for idempotency cache                                                           | `0`                                                           |
| `REDIS_PASSWORD`         | Redis password for idempotency cache                                                     | —                                                             |
| `IDEMPOTENCY_TTL`        | Cached response and key-owner TTL                                                        | `86400`                                                       |
| `IDEMPOTENCY_ENABLED`    | Enable shared idempotency middleware                                                     | `true`                                                        |
| `IDEMPOTENCY_ENFORCE_REQUIRED_KEYS` | Require keys for `required_replay` routes                                        | `true`                                                        |
| `IDEMPOTENCY_LOCK_TTL`   | Redis lock TTL for in-flight requests                                                    | `10`                                                          |
| `IDEMPOTENCY_WAIT_TIMEOUT` | Wait time for an in-flight cached replay                                               | `10.0`                                                        |
| `CHAT_RUN_REPLAY_TTL_SECONDS` | How long a finished chat run's events stay replayable in Redis (valid range 600–1800) | `600` |
| `CHAT_RUN_LEASE_TTL_SECONDS` | Chat-run worker lease TTL; a run whose owner stops renewing is reaped | `10.0` |
| `CHAT_RUN_HEARTBEAT_SECONDS` | How often a run's owner renews its lease and checks the cross-instance cancel flag | `2.0` |
| `CHAT_RUN_MAX_EVENTS` | Frames kept per run event log (Redis Stream trim) | `50000` |
| `CHAT_RUN_CANCEL_GRACE_SECONDS` | Cooperative-cancel window before a Stop escalates to a hard cancel | `5.0` |
| `CHAT_RUN_SHUTDOWN_GRACE_SECONDS` | Time a graceful shutdown waits for live runs before interrupting them | `20.0` |
| `CHAT_RUN_REAPER_INTERVAL_SECONDS` | How often each instance reaps orphaned runs whose lease expired | `10.0` |
| `CHAT_RUN_MAX_DURATION_SECONDS` | Hard lifetime cap for a single chat run | `3600` |

---

## RAG Service (`configs/.env`)

| Variable                 | Description                               | Default                                                       |
| ------------------------ | ----------------------------------------- | ------------------------------------------------------------- |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_RAG_SERVICE_USER` / `POSTGRES_RAG_SERVICE_PASSWORD` / `POSTGRES_RAG_SERVICE_DB` | PostgreSQL connection parts (the service assembles the DSN itself; its bootstrap creates the role and the database) | `localhost` / `8124` / `postgres` / generated / `rag_service` |
| `MILVUS_HOST`            | Milvus hostname                           | `localhost`                                                   |
| `MILVUS_PORT`            | Milvus port                               | `19530`                                                       |
| `MILVUS_ALIAS`           | Milvus connection alias                   | `default`                                                     |
| `NEO4J_URI`              | Neo4j connection URI                      | `bolt://localhost:7687`                                       |
| `NEO4J_USER`             | Neo4j username                            | `neo4j`                                                       |
| `NEO4J_PASSWORD`         | Neo4j password                            | —                                                             |
| `OLLAMA_BASE_URL`        | Ollama server URL                         | `http://localhost:11434`                                      |
| `EMBEDDING_PROVIDER`     | Embedding provider (`ollama` or `openai`) | `ollama`                                                      |
| `EMBEDDING_MODEL`        | Embedding model name                      | `nomic-embed-text`                                            |
| `OPENAI_API_KEY`         | OpenAI API key for embeddings             | —                                                             |
| `LLM_PROVIDER`           | LLM provider for graph extraction         | `ollama`                                                      |
| `LLM_MODEL`              | LLM model for graph extraction            | `llama3`                                                      |
| `INTERNAL_SERVICE_TOKEN` | Service-to-service auth token             | —                                                             |
| `SERVICE_NAME`           | Service identifier                        | `rag-service`                                                 |
| `LOG_LEVEL`              | Logging level                             | `INFO`                                                        |
| `HOST`                   | Server bind address                       | `0.0.0.0`                                                     |
| `PORT`                   | Server port                               | `8083`                                                        |
| `REDIS_HOST`             | Redis host for idempotency cache          | `localhost`                                                   |
| `REDIS_PORT`             | Redis port for idempotency cache          | `6379`                                                        |
| `REDIS_DB`               | Redis DB for idempotency cache            | `0`                                                           |
| `REDIS_PASSWORD`         | Redis password for idempotency cache      | —                                                             |
| `IDEMPOTENCY_TTL`        | Cached response and key-owner TTL         | `86400`                                                       |
| `IDEMPOTENCY_ENABLED`    | Enable shared idempotency middleware      | `true`                                                        |
| `IDEMPOTENCY_ENFORCE_REQUIRED_KEYS` | Require keys for `required_replay` routes | `true`                                                   |
| `IDEMPOTENCY_LOCK_TTL`   | Redis lock TTL for in-flight requests     | `10`                                                          |
| `IDEMPOTENCY_WAIT_TIMEOUT` | Wait time for an in-flight cached replay | `10.0`                                                       |

---

## Tools Service (`configs/.env`)

| Variable                 | Description                        | Default                                                       |
| ------------------------ | ---------------------------------- | ------------------------------------------------------------- |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_TOOL_SERVICE_USER` / `POSTGRES_TOOL_SERVICE_PASSWORD` / `POSTGRES_TOOL_SERVICE_DB` | PostgreSQL connection parts (the service assembles the DSN itself; its bootstrap creates the role and the database) | `localhost` / `8124` / `postgres` / generated / `tools_service` |
| `INTERNAL_SERVICE_TOKEN` | Service-to-service auth token      | —                                                             |
| `INTERNAL_USER_SERVICE_URL` | Internal user-service gateway URL | — |
| `SERVICE_NAME`           | Service identifier                 | `tools-service`                                               |
| `LOG_LEVEL`              | Logging level                      | `INFO`                                                        |
| `HOST`                   | Server bind address                | `0.0.0.0`                                                     |
| `MCP_PORT`               | MCP server port                    | `8001`                                                        |
| `PYTHON_CMD`             | Python interpreter path            | `python3`                                                     |
| `WORKING_DIR`            | MCP working directory              | `/tmp/mcp`                                                    |
| `ALLOWED_ORIGINS`        | CORS origins                       | `*`                                                           |
| `REDIS_HOST`             | Redis host for idempotency cache   | `localhost`                                                   |
| `REDIS_PORT`             | Redis port for idempotency cache   | `6379`                                                        |
| `REDIS_DB`               | Redis DB for idempotency cache     | `0`                                                           |
| `REDIS_PASSWORD`         | Redis password for idempotency cache | —                                                           |
| `IDEMPOTENCY_TTL`        | Cached response and key-owner TTL  | `86400`                                                       |
| `IDEMPOTENCY_ENABLED`    | Enable shared idempotency middleware | `true`                                                      |
| `IDEMPOTENCY_ENFORCE_REQUIRED_KEYS` | Require keys for `required_replay` routes | `true`                                                   |
| `IDEMPOTENCY_LOCK_TTL`   | Redis lock TTL for in-flight requests | `10`                                                       |
| `IDEMPOTENCY_WAIT_TIMEOUT` | Wait time for an in-flight cached replay | `10.0`                                                 |

---

## Web Frontend

The web frontend reads from the shared `configs/.env` like every other
service (via Compose `env_file` or the config_manager loader in local runs). There is
no per-service `.env` file.

| Variable                         | Description                                              | Default                                            |
| -------------------------------- | -------------------------------------------------------- | -------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`            | Browser-facing APISIX base URL for compatibility API calls | `http://localhost:8000/api`                        |
| `AGENT_SERVICE_URL`              | Explicit server-side agent-service gateway base          | `http://localhost:8000/agent-service`              |
| `USER_SERVICE_URL`               | Server-side user-service gateway base                    | `http://localhost:8000/user-service`               |
| `RAG_SERVICE_URL`                | Web runtime RAG gateway base                             | `http://localhost:8000/rag-service`                |
| `MCP_INTERNAL_URL`               | Server-side internal MCP gateway URL                     | `http://localhost:8000/internal/tools-service/mcp` |
| `TOOLS_SERVICE_URL`              | Server-side tools-service MCP gateway URL                | `http://localhost:8000/tools-service/mcp`          |
| `NEXT_PUBLIC_WS_URL`             | WebSocket URL for streaming                              | `ws://localhost:8000`                              |
| `NEXT_PUBLIC_KEYCLOAK_URL`       | Keycloak external URL                                    | `http://localhost:8080`                            |
| `NEXT_PUBLIC_KEYCLOAK_REALM`     | Keycloak realm                                           | `agenticai-v1`                                     |
| `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID` | Keycloak client ID for frontend                          | `web-client`                                       |
| `SENTRY_AUTH_TOKEN`              | Sentry auth token (optional)                             | —                                                  |
| `NEXT_PUBLIC_SENTRY_DSN`         | Sentry DSN (optional)                                    | —                                                  |
| `NEXT_PUBLIC_ANALYTICS_ID`       | Analytics ID (optional)                                  | —                                                  |

The four explicit backend service roots, `MCP_INTERNAL_URL`, `GATEWAY_URL`, and
`WEB_DOMAIN` are required web configuration rather than runtime fallbacks.
They must share the APISIX origin and carry the gateway paths listed above;
direct service addresses fail startup validation. Domain `endpoints.ts` files
own backend paths, and the central HTTP layer joins them to the selected
service root. Application code reads only the typed settings exposed by
`src/lib/settings.ts`; `INTERNAL_URL`, `LANGCONNECT_URL` and `MCP_SERVER_URL`
are obsolete and no longer declared by the central catalog (remove them from an
existing `configs/.env`). Do not remove internal service settings from backend
environments.

Sentry is only enabled when **both** `SENTRY_AUTH_TOKEN` and `NEXT_PUBLIC_SENTRY_DSN` are set. If missing, Sentry is no-op.

---

## Encryption keys

Each class of stored secret is sealed under its own Fernet key, so a leaked key
opens only its own data:

| Key | Protects |
| --- | --- |
| `LLM_PROVIDER_API_ENCRYPTION_KEY` | `user_provider_configs.api_key_encrypted` |
| `MCP_CREDENTIAL_ENCRYPTION_KEY` | `mcp_provider_auth.credentials_encrypted`, `.oauth_access_token_encrypted`, `.oauth_refresh_token_encrypted` |
| `MCP_OAUTH_ENCRYPTION_KEY` | `mcp_oauth_session.client_secret_encrypted` |
| `MAIL_CONFIG_ENCRYPTION_KEY` | `mail_config.password_encrypted`, `user_mail_credential.password_encrypted` |
| `USER_API_KEY_ENCRYPTION_KEY` | `api_keys.key_hash` |
| `SYSTEM_SETTINGS_ENCRYPTION_KEY` | the `*_ENCRYPTED` members of `system_settings.value` |
| `CONNECTOR_CONFIG_ENCRYPTION_KEY` | `user_connector_configs.config_encrypted` |

A missing key fails the service at startup rather than falling back to another
key, which would defeat the separation.

Each scope reads and writes only with its own key. Ciphertext encrypted under
the former shared key cannot be decrypted; reset or replace those stored
credentials before using them again.

## Startup helper commands

```sh
# Provide missing keys and credentials in configs/.env manually

# Validate the shared configuration
make env-check
```

---

## Common variable groups across services

### Gateway trust shared by services

Gateway authenticates callers with Keycloak and forwards trusted identity.
Backend services do not use shared JWT signing or verification keys.

| Variable | Where set | Purpose |
| --- | --- | --- |
| `INTERNAL_SERVICE_TOKEN` | `configs/.env` | Shared proof of Gateway traversal and machine-call credential |

### Database (user-service, agent-service)

Services share `POSTGRES_HOST` and `POSTGRES_PORT`, but each uses its own
`POSTGRES_<service>_SERVICE_USER`, `PASSWORD`, and `DB` values. User-service
always uses `POSTGRES_USER_SERVICE_DB`, including for migration connections.

### LLM providers (agent-service, rag-service)

| Variable          | agent-service                   | rag-service                      |
| ----------------- | ------------------------------- | -------------------------------- |
| `OPENAI_API_KEY`  | Chat models (GPT-4o)            | Embeddings (text-embedding-3-\*) |
| `OLLAMA_BASE_URL` | Chat models                     | Embeddings + graph LLM           |
| Custom provider   | Per-agent API key storage in DB | Not supported                    |
