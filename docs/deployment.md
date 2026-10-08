# Deployment

## Gateway architecture upgrade

The Gateway image now includes an APISIX plugin that calls Keycloak directly for
login, token introspection, and UMA authorization decisions. Build the custom
image with the repository's stack workflow; the stock APISIX image does not
contain this plugin. APISIX uses standalone YAML mode without an admin API.

Before restarting the stack, configure the required
[Gateway settings](env-variables.md#gateway-authentication-and-organization-orchestration).
Gateway waits for Redis and the Keycloak bootstrap job. Bootstrap provisions
the confidential Gateway client, token audience mappers, and authorization
resources, scopes, and role policies. It removes Keycloak's default permissive
authorization policy. Existing tokens issued without the Gateway audience need
a refresh or a new login.

Gateway loads `configs/apisix/gateway-policies.json`. Regenerate this inventory
when route paths, methods, or permission dependencies change:

```sh
python scripts/gateway_authorization.py --output configs/apisix/gateway-policies.json
```

Re-run bootstrap to reconcile Keycloak's feature policies and reload Gateway to
load the new inventory. The inventory is bind-mounted as a single file, so a
running Gateway container keeps the copy it mounted when it was created:
`docker restart apisix` keeps the stale inventory, and after the host file is
replaced the container can even fail to mount. Recreate it instead:

```sh
make gateway-reload
```

Until the inventory is reloaded, every route that exists only in the new file is
denied with a 403 `ResponseModel` error (`error.code` `auth.forbidden`) — for example the knowledge-search
routes under `/rag-service/api/v1/search`. Unknown routes and unavailable
identity-provider decisions fail closed. Browser login uses one-time Redis state
and PKCE; external identity-provider login redirects through the Keycloak broker.

User-service projects direct agent and collection assignments into Keycloak
authorization resources at startup and after assignment changes. It excludes
inactive organizations and reconciles organization and user deletion. Startup
fails if this projection cannot complete. SQL remains the assignment source.

For organization workspace saves, only the affected resources' managed scope
permissions are cleared before SQL changes and rebuilt afterward. Other subjects'
grants to those resources are preserved, and unrelated agent and collection grants
are not rewritten. Shared subject policies and resource objects are reused.
Startup and unscoped cleanup operations retain full reconciliation.

Scoped saves record affected resource IDs in Redis under
`agentic:keycloak:<realm>:resource-projection:<resource-type>:<target-type>:<target-id>`
while holding the shared policy-write lock. Entries have no expiry and are removed
only after successful projection. Retrying a failed save for the same target also
repairs removed resources whose SQL assignments have already committed. Preserve
these recovery entries after a failed save; do not clear them as ordinary cache
data. Failed writes propagate an error, and stale grants are not restored.

Bootstrap, role changes, and resource assignment changes share a Redis lock.
All writers must use the same Redis database. The lock has no expiry to prevent
overlapping writers; acquisition fails after five seconds. If a writer crashes,
stop all policy writers and verify that none remains active before removing the
`agentic:keycloak:<realm>:feature-policy-write` key from that database. Re-run
bootstrap and restart user-service to rebuild feature and resource grants before
resuming administration.

Backend services retain resource and tenant checks. Internal bearer calls use
Keycloak authorization; machine-only calls must supply the internal credential.
Restrict backend network access to trusted infrastructure. Compose service URLs
route through Gateway, but URL configuration is not a network firewall.
Development backend debug ports bind to loopback; production application
services do not publish backend ports. The infrastructure Compose file publishes
PostgreSQL, Keycloak, Redis, Neo4j, MinIO, Milvus and Ollama on the loopback
interface only: each port binds to `${<SERVICE>_BIND_ADDR:-127.0.0.1}`
(`POSTGRES_BIND_ADDR`, `KEYCLOAK_BIND_ADDR`, `REDIS_BIND_ADDR`, `NEO4J_BIND_ADDR`,
`MINIO_BIND_ADDR`, `MILVUS_BIND_ADDR`, `OLLAMA_BIND_ADDR`, all `127.0.0.1` in the
central catalog). A shared server that developers reach remotely sets the keys
of the services it means to expose to `0.0.0.0` or to its interface address in
its own `configs/.env`; Keycloak needs that (or a reverse proxy in front) as soon
as a browser outside the host has to complete the OIDC login. APISIX (`8000`)
stays published on all interfaces: it is the edge.

Python service images install the shared `env` configuration package (`packages/config-manager`).
Backend Compose definitions under `deploy/docker/` read `configs/.env` at
runtime and use the repository root as their build context. The real env file
is excluded from image builds. Container environment overrides continue to
take precedence over file values. Compose containers connect to Redis through
the `redis` service name; host-run processes can keep using `localhost` from
`configs/.env`.

APISIX reads its Redis hostname from `REDIS_HOST_CONTAINER` in `configs/.env`;
set it to `redis` for the Compose network. Its Compose block reads image tags,
the public port, and Gateway settings from the environment without fallback
values. Set these keys before starting the stack; optional values can be empty.

### Proxy behaviour at the edge

`configs/apisix/apisix.yaml` fixes how the gateway talks to the services:

- Every upstream must accept the connection within 5 s; a service that is
  down answers `502`/`504` in seconds, not after a minute. `retries` is not
  set, and APISIX's default is the node count minus one: with one node per
  upstream the gateway never retries a request. Callers that want a retry
  keep their own (`configs/resilience.yaml` for the services).
- Read and send timeouts are 60 s, and 600 s on agent-service and
  tools-service, whose chat and MCP routes stream. Those routes
  (`agent-service-protected`, `tools-service-mcp`, `internal-tools-service`)
  also disable response buffering with the `proxy-buffering` plugin, and
  `configs/apisix/config.yaml` sets `proxy_request_buffering off` for every
  route, so uploads and event streams pass through without being spooled.
- Upstreams use `pass_host: node`: a service sees the upstream address as
  `Host` and the browser's host in `X-Forwarded-Host`. No service reads
  either, so a service that starts to must take the public host from
  `X-Forwarded-Host`, or the upstream must switch to `pass_host: pass`.
- A `502`/`503`/`504` that the gateway generates itself (upstream down or
  too slow) carries nginx's HTML page, not the `ResponseModel` envelope; the
  errors the `gateway-auth` plugin answers do carry the envelope. The web
  replaces such markup bodies with its own status message, so API clients
  must be ready for a non-JSON body on these statuses as well.
- The gateway adds nothing else: no rate limiting, CORS, request-size limit
  or IP restriction. Those belong to the services, or to a proxy in front
  of APISIX.

Backend Compose overrides use `INTERNAL_*_URL` keys for calls through the
internal gateway routes. Keep unprefixed service URLs for web runtime and
public MCP metadata. In local backend runs, configure the same internal keys
in `configs/.env`; tools-service connector resolution also requires
`INTERNAL_AGENT_SERVICE_URL` ending in `/internal/agent-service/api/v1`.

## Deployment model

The platform is deployed as Docker containers orchestrated with Docker Compose. There is no Kubernetes or CI/CD pipeline configured (`.github/` is empty). All validation is local via Makefile quality gates.

---

## Connector tool upgrade

Apply agent-service migration `0046` before starting the updated application.
It adds an empty `connector_bindings` list to existing personas. Rebuild
tools-service to install its connector client dependencies, and refresh the
APISIX configuration to include the internal connector-resolution route.

Both Compose environments provide the internal agent-service URL to
tools-service. Saved connector configurations are read from user-service, where
they are stored encrypted per user; agent-service translates them into the shape
the tools-service adapter reads. See
[connector runtime variables](env-variables.md#saved-connector-runtime).

## Connector runtime upgrade (Airbyte removal)

Datasource syncs run inside agent-service through `packages/connector-py`;
there is no Airbyte deployment, custom destination image, or Docker socket mount
any more.

1. Generate `CONNECTOR_CONFIG_ENCRYPTION_KEY` (a Fernet key) and add it to
   `configs/.env` and to every environment's secret store before starting
   user-service.
2. Apply user-service migration `0051` (`user_connector_configs`) and
   agent-service migrations `0051` and `0052`. `0051` creates
   `datasource_connections`, `connector_sync_jobs` and
   `connector_sync_state`, drops `datasource_airbyte_mapping` and renames the
   flow component `AirbyteDatasource` to `ConnectorDatasource`; `0052` adds
   the partial unique index `uq_connector_sync_jobs_active` (one pending or
   running sync job per datasource). All run at service startup. Should a
   datasource already have several live jobs, `0052` keeps the newest and
   closes the others as failed ("superseded by a newer sync job") before it
   builds the index.
3. Refresh the APISIX configuration once the Keycloak bootstrap (the
   `keycloak-bootstrap` compose service) has reconciled the realm:
   `make gateway-reload`. The internal ingest routes are gone; the policy
   inventory carries the internal connector-configuration routes and the two
   rag-service routes the connector runtime calls at the end of an `overwrite`
   sync and when a datasource is deleted
   (`POST /api/v1/datasources/{id}/records/retire`,
   `DELETE /api/v1/datasources/{id}/records`). An APISIX still running the old
   configuration answers those two calls with 403: the sync's closing sweep and
   the datasource delete fail until the configuration is reloaded.
4. Remove every `AIRBYTE_*` key from the environment. The old Airbyte
   containers, the `airbyte` database, and the `airbyte-workspace` /
   `airbyte-data` volumes are no longer used and can be deleted once nothing
   needs to be read back from them.

Existing datasources keep their collection and chunks. Their configuration
lived in Airbyte's database in that connector's own shape and is not migrated:
save the configuration again on each datasource (`PUT /datasources/{id}` with
`connector_config`) before its next sync. Connector names no longer carry the
`source-` prefix (`postgres`, not `source-postgres`).

Two more things lived in Airbyte and are gone with it; migration `0051` does
not mention them because this database never held them:

- Sync schedules. Airbyte ran them from its own database, so `sync_schedules`
  has no row for such a datasource. Create the schedule again
  (`POST /datasources/{id}/schedule`, or the datasource's schedule dialog)
  after its configuration is saved; the schedule API refuses a datasource
  without a connection. An enabled row that does exist is armed again, at
  the next agent-service start at the latest, once its datasource has a
  connection: disable the ones that should stay off before saving
  configurations.
- The Graph-RAG flag (`update_graph_rag`) was a column of the dropped
  mapping. It is set through the schedule body (`POST`/`PUT
  /datasources/{id}/schedule`) and stored on the connection; set it again
  where the knowledge graph should follow the sync.

Before the rollout, list the connector types in use and compare them with
the built-in catalog (`GET /datasources/connectors`). A collection can be
given a configuration only when its `connector_type` is a catalog name,
read with the `source-` prefix dropped and `-` as `_`
(`source-google-drive` → `google_drive`). Every other datasource answers
`400` (`datasource.no_connection`) to sync, rename and stream edits until it
is recreated with a catalog connector, so list those for their owners:

```sql
SELECT DISTINCT cmetadata->>'connector_type' AS connector_type
FROM langchain_pg_collection
WHERE coalesce(cmetadata->>'connector_type', '') <> '';
```

Operational notes:

- `CONNECTOR_MAX_CONCURRENT_SYNCS` (default `1`) bounds parallel syncs per
  agent-service process; further syncs wait as pending jobs.
- `CONNECTOR_SYNC_TIMEOUT_SECONDS` (default `86400`, `0` for no limit) fails a
  sync that runs longer, so a source that hangs gives its slot back. Raise it
  where a full refresh legitimately takes more than a day.
- A sync interrupted by a restart is resumed from its last checkpoint. With
  several replicas, a sync whose process died is picked up after its heartbeat
  has been silent for 90 seconds. Large ordered streams (database tables, file
  trees) also save checkpoints while they are read, so the rerun continues
  near where the sync stopped.
- A datasource has one live sync job at a time, across replicas; the database
  enforces it. A trigger that arrives while a job is pending or running starts
  nothing.
- A connector configuration is read from user-service when a sync job starts
  running, and once up front when a sync triggered by hand is about to start
  (to refuse a trigger whose configuration is gone). A trigger refused because
  a job is already pending or running, scheduler polls and status lookups never
  read it. User-service must be reachable at those moments; a job whose
  configuration cannot be found fails with a message asking to save the
  datasource configuration again.
- Sync batches are written to rag-service with idempotency keys made of
  letters, digits, `.`, `_` and `-` only, the alphabet its middleware accepts.
  The reason of a failed sync is stored and shown without URL query strings,
  URL passwords and the connector's secret values.
- rag-service keeps one version of a record. Every document of a sync batch
  carries a record key (the primary-key values of its stream, or the whole
  record when it has none), and a record that is written again replaces the
  chunks stored for it. A batch that rag-service failed with `429` or `5xx` is
  retried inside the job, and a job that runs again after a failure does not
  store a second copy of what the failed one had written. Deploy rag-service
  and agent-service together: either one alone keeps appending.
- Chunks written before record keys existed carry none and are never
  replaced: the first sync after the upgrade stores its records next to them.
  Run one `full_refresh` + `overwrite` sync per datasource to clear them.
- A stream with a primary key under `append` holds one version of each record,
  so the chunk count of such a datasource no longer grows with every sync and
  goes down the first time changed records arrive. A record without a primary
  key (every record of a file stream is one) is replaced only when it comes
  again unchanged; a changed one is stored next to its old version.
- Replacing costs one lookup and one delete in Milvus per batch. The lookup
  filters on `metadata["_record_key"]`, and rag-service asks Milvus for a JSON
  path index on it (`record_key`, type `INVERTED`) at the first write with
  record keys: about once per collection in each rag-service process, and a
  repeated request is accepted. Milvus builds the index in the background,
  also on a collection that already holds chunks (about 18 s at 1 000 000
  chunks), and no write waits for it; until it is built the lookup scans. It
  needs Milvus 2.5.10 or later (JSON path indexes arrived in 2.5.7 and did not
  work for string filters before 2.5.10; the compose file runs v2.5.11). When
  Milvus refuses the request, rag-service logs a warning on every such write
  and the lookup keeps scanning: slower, not wrong. Measured on v2.5.11 with
  200 record keys per lookup at 1 000 000 chunks: about 400 ms median (410 ms
  p95) with the index, 602 ms (794 ms) without. What is left with the index
  is Milvus' wait for strong consistency (200-400 ms), which the lookup needs
  to see chunks written a moment earlier.
- Connectors that read the service's own filesystem (`jsonl_file`,
  `file_upload`, `file_server`) are hidden unless named in `CONNECTORS_ENABLED`.
- Connectors open network connections from the agent-service container. Treat
  `datasource:create` and `datasource:update` as administrative permissions and
  restrict the container's egress where the network allows it.
- The agent-service image carries the drivers of the `mssql` connector (pyodbc
  with Microsoft ODBC Driver 18) and of the `spark` connector (the Spark Connect
  client `pyspark-client` and the Thrift Server client `pyhive`). The ODBC
  driver is installed from `packages.microsoft.com` while the image is built,
  under Microsoft's licence terms (`ACCEPT_EULA=Y` in
  `apps/agent-service/docker/Dockerfile.service`); a build host without access
  to that repository needs a mirror of it. The Spark Connect client is a 4.x
  client and has not been run against a 3.x server; the `thrift` transport does
  not depend on the Spark version.

## Infrastructure upgrade

The infrastructure compose file moves PostgreSQL from 15 to 18 (`postgres:18`,
also for `keycloak-db-init`), Keycloak from 26.1 to 26.8
(`quay.io/keycloak/keycloak:26.8`) and Redis from 7 to 8.10 (`redis:8.10-alpine`).
A fresh installation needs nothing beyond the new compose file. Existing data
needs the steps below, in this order: each step is one-way on its own data
(PostgreSQL data directory, Keycloak schema, Redis dump format), Keycloak's
database lives on the PostgreSQL server, and a failure has to be attributable
to one step. Every step names its way back. The procedure was rehearsed step by
step with throwaway data (a bootstrap realm, an application database with
20 000 rows, Redis keys with and without expiry); the timings below come from
that rehearsal on a laptop.

`dc` stands for
`docker compose --env-file configs/.env -f deploy/docker/docker-compose-services.yml`.
Read credentials inside the containers (`$POSTGRES_USER`, `$REDIS_PASSWORD`)
instead of sourcing `configs/.env`: its JSON values break `source`.

### What changed in the compose file

- PostgreSQL: the volume is mounted at `/var/lib/postgresql` and the data
  directory is the image's default for its major version
  (`/var/lib/postgresql/18/docker`). `POSTGRES_PGDATA` is gone from
  `configs/.env` and from `config_manager`; the 15 cluster of an existing volume
  sits in its `pgdata` directory. A guard in the service's entrypoint refuses
  to start when the volume holds the data of another major version and the 18
  directory does not exist, because the image would otherwise create an empty
  cluster and start with empty databases. The container then exits with
  `PostgreSQL 15 data in /var/lib/postgresql/pgdata and none in
  /var/lib/postgresql/18/docker: not starting with empty databases.`, restarts
  in a loop, and every dependent service fails with `dependency failed to start:
  container postgres is unhealthy`. Step 3 creates the 18 cluster on purpose.
  The service no longer sets `POSTGRES_DB`: a database the image creates at
  init belongs to the admin role, and from PostgreSQL 15 on only the owner may
  create tables in its `public` schema, so user-service's migrations failed on
  a fresh volume with `permission denied for schema public`. Each service's
  bootstrap creates its own database with the service role as owner.
- Keycloak: the health check asks `GET /health/ready` on the management port
  9000 (shell builtins; the image has no curl) and needs
  `KEYCLOAK_HEALTH_ENABLED=true` (the default). The old check tested that PID 1
  is `java`: it reported healthy before Keycloak answered, so
  `keycloak-bootstrap` could run too early and exit 1 (also on 26.1), and after
  a restart of 26.4 or later it stayed unhealthy because PID 1 is `kc.sh`.
  `start_period` is 180 s: the first start on an existing realm migrates the
  database. The container reads `KC_BOOTSTRAP_ADMIN_USERNAME` /
  `KC_BOOTSTRAP_ADMIN_PASSWORD` from the unchanged keys `KEYCLOAK_ADMIN` /
  `KEYCLOAK_ADMIN_PASSWORD` (the old container variables have been deprecated
  since 26.0 and are logged as such).
- Redis: the tag only. `redis:8.10-alpine` declares no volume; data is kept in
  `redis-data`, mounted at `/data`, as before.
- `scripts/tests/check_gateway_integration.py` runs the Keycloak and Redis
  images of the compose file.

### 1. Backups, with the old stack running

```sh
docker exec postgres sh -c 'pg_dumpall -U "$POSTGRES_USER"' > postgres-15-all.sql
docker exec postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc -f /tmp/keycloak-26.1.dump keycloak'
docker cp postgres:/tmp/keycloak-26.1.dump .
docker exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning SAVE'
docker cp redis:/data/dump.rdb redis-7-dump.rdb
```

`keycloak` is `KEYCLOAK_DB_NAME`. Keep a copy of the compose file of before
this upgrade, taken from the previously deployed tag; it is the way back of
steps 2 to 4:

```sh
git show PREVIOUS_TAG:deploy/docker/docker-compose-services.yml > compose-old.yml
```

It still reads `POSTGRES_PGDATA=/var/lib/postgresql/data/pgdata`, which the
new `configs/.env` no longer has; give it that key in a second `--env-file`.

### 2. Keycloak 26.8, still on PostgreSQL 15

```sh
dc up -d --no-deps keycloak
```

Only Keycloak is recreated. The first start migrates the realm (log:
`migrated realm ... to 26.8.0`; the keycloak database grows from 87 to 101
tables) and reached healthy about 100-120 s after the command in the rehearsal.
Verify: users log in through the gateway, a refresh token issued before the
step still refreshes, `docker logs keycloak` shows no `ERROR`. The bootstrap
runs again in step 5.

Way back: stop Keycloak, put the database of before the step back, start the
old image with the old compose file.

```sh
dc stop keycloak
docker cp keycloak-26.1.dump postgres:/tmp/keycloak-26.1.dump
docker exec postgres sh -c 'dropdb -U "$POSTGRES_USER" keycloak && createdb -U "$POSTGRES_USER" keycloak && pg_restore -U "$POSTGRES_USER" -d keycloak /tmp/keycloak-26.1.dump'
docker compose --env-file configs/.env -f compose-old.yml up -d --no-deps keycloak
```

### 3. PostgreSQL 15 to 18, by dump and restore

The data moves with `pg_dumpall` of the 18 client against the running 15
server and `psql` into a new 18 cluster: no second set of binaries in the
container, indexes are rebuilt (no collation question), and the new cluster has
data checksums on. `pg_upgrade` is not used.

Stop every writer first: Keycloak (`dc stop keycloak`) and the application
services (their compose files, or `docker stop`). Then check that no role has
an MD5 password (MD5 authentication is deprecated in 18; reset such passwords
before the move) and that nothing else is connected:

```sh
docker exec -i postgres sh -c 'psql -U "$POSTGRES_USER" -At' <<'SQL'
select count(*) as md5_passwords from pg_authid where rolpassword like 'md5%';
select usename, application_name from pg_stat_activity where backend_type = 'client backend' and pid <> pg_backend_pid();
SQL
```

Both answers must be empty (`0` and no row). Dump with the 18 client (the
container shares the network namespace of `postgres`, so `127.0.0.1` is the
server and the connection is trusted):

```sh
ADMIN=$(docker exec postgres sh -c 'printf %s "$POSTGRES_USER"')
docker run --rm --network container:postgres postgres:18 pg_dumpall -h 127.0.0.1 -U "$ADMIN" > postgres-15-for-18.sql
```

Rehearsal: 3.5 MB in 8 s, nothing on stderr. Now replace the server. No
`postgres` container may be running or restarting on the volume while the 18
cluster is created: a container in the guard's restart loop would start the
server as soon as the directory appears.

```sh
dc stop postgres
dc rm -f postgres
dc run --rm --no-deps --entrypoint docker-ensure-initdb.sh postgres   # creates /var/lib/postgresql/18/docker next to pgdata
dc up -d postgres                                                    # healthy after about 10 s
docker exec -i postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres' < postgres-15-for-18.sql
docker exec postgres sh -c 'vacuumdb -U "$POSTGRES_USER" --all --analyze-in-stages'
```

`docker-ensure-initdb.sh` does not go through the guard; running it a second
time is a no-op. The new cluster starts with the database `postgres` and one
named after the admin role (the image creates no other database; see "What
changed"). The restore prints exactly one expected error, `role
"<POSTGRES_ADMIN_USER>" already exists`; a `database "..." already exists`
line can only appear for a database that both clusters have, and anything
else has to be read. Rehearsal: 11 s for the 3.5 MB dump. Verify before going
on:

```sh
docker exec -i postgres sh -c 'psql -U "$POSTGRES_USER" -At' <<'SQL'
show server_version;
show data_checksums;
select datname, pg_get_userbyid(datdba) from pg_database where not datistemplate order by 1;
SQL
```

Compare roles, databases, owners and row counts with the 15 server; the
rehearsal kept all of them, the encodings and locales, the index validity, the
identity-column positions and the application role's password. Then
`dc up -d --no-deps keycloak` (healthy in about 30 s on the moved data).

The 15 cluster stays in `pgdata` of the volume (109 MB in the rehearsal). Way
back: stop the stack, start the old compose file, which opens `pgdata` with the
old image; everything written to 18 after the move is not in it. Once the 18
server has been running for a while, reclaim the space:

```sh
dc stop postgres
docker run --rm -v langgraph-with-ui_postgres-vanilla-data:/v alpine:3.20 rm -rf /v/pgdata
dc up -d postgres
```

### 4. Redis 8.10 on the same volume

```sh
dc up -d --no-deps redis
```

8.10 loads the file of 7 (`Loading RDB produced by version 7.4.x`); keys,
expiries and the keys without expiry (the policy-write lock, the projection
journals) stay. Do not wipe the volume. While Redis restarts, routes that
require idempotency and the gateway login answer 503. The image loads the
JSON, search, bloom, time-series and vector-set modules (about 25 MB more RSS
on an empty server); the services need none of them.

Way back: after the first `SAVE` or shutdown of 8.10 the file is RDB version
15, which 7 refuses (`Can't handle RDB format version 15`, restart loop).
Stop Redis, copy the saved file of step 1 into the stopped container, start
the old image: `dc stop redis`, `docker cp redis-7-dump.rdb redis:/data/dump.rdb`,
old compose file `up -d --no-deps redis`.

### 5. The rest of the stack

```sh
dc up -d
```

recreates `keycloak-db-init` on `postgres:18` and runs `keycloak-bootstrap`
again (idempotent, exit 0). Start the application services; they run their
migrations at startup and this upgrade adds none. Verify the gateway login,
the health checks below and a Keycloak restart (`docker restart keycloak`,
healthy in 20-30 s, sessions kept).

### Behaviour that changes with the new versions

- Keycloak 26.8 answers `400 missingNormalization` to request paths with `//`
  or `/./`; trailing slashes are fine. `KEYCLOAK_BASE_URL` and
  `KEYCLOAK_ISSUER_URL` carry no trailing slash.
- Keycloak 26.8 validates realm session settings: a client session idle or
  max lifespan above the SSO value is refused with 400 (26.1 stored it). The
  user-service settings endpoint reports it as `keycloak_realm_update_failed`.
- Keycloak 26.8 logs `Client '<login client>' ... 'Full scope allowed' switch
  ... deprecated` on every token until `keycloak-bootstrap` has run once with
  the current scripts: the bootstrap now turns the switch off and maps only the
  platform realm roles (`system-admin`, `enterprise-admin`, `enduser`) into the
  login tokens. Tokens issued afterwards carry no `resource_access` and no
  built-in roles (`offline_access`, `uma_authorization`, `default-roles-*`);
  Gateway and the services need none of them. The image's deprecated-feature
  notices remain.
- Enabling authorization services on a client through the Admin API no longer
  creates the `Default Resource`, `Default Policy` and `Default Permission`;
  user-service removes them at startup anyway.
- PostgreSQL 18 lists NOT NULL constraints in `pg_constraint` and creates new
  clusters with data checksums; none of the services' migrations or tests
  behaved differently on 18 than on 15.

## Environments

| Environment | Compose file | Purpose |
|-------------|-------------|---------|
| Development | `deploy/docker/docker-compose-dev.yml` | Local dev with hot-reload |
| Production | `deploy/docker/docker-compose-prod.yml` | Production deployment |

## Local deployment

### Prerequisites

- Docker + Docker Compose
- A working NVIDIA GPU driver (`nvidia-smi`) and NVIDIA Container Toolkit for
  the Compose-managed Ollama service
- An existing external Docker volume named `ollama` for Ollama model data
- Python 3.11+ with `uv` installed
- Node.js 20+ (for frontend)
- At least 8GB RAM, 20GB disk
- The host kernel parameter `vm.max_map_count` set to at least `262144` for
  Elasticsearch (`sudo sysctl -w vm.max_map_count=262144`; make it permanent in
  `/etc/sysctl.conf`)

### Step-by-step

```sh
# 1. Clone and provide configs/.env manually
make env-check

# 2. Start third-party services, pull Ollama models, and start app services
make stack-up

# 3. Verify everything is running
curl http://localhost:8000/user-service/health
curl http://localhost:8000/user-service/health/ready
curl http://localhost:8000/agent-service/health
curl http://localhost:8000/rag-service/health
curl http://localhost:8000/tools-service/health
```

### Running services outside Docker (for development)

```sh
# Each service in its own terminal:
make -C apps/user-service run        # User Service on :8090
make -C apps/agent-service run        # Agent Service on :8080
make -C apps/rag-service run          # RAG Service on :8083
make -C apps/tools-service run        # Tools Service on :8001
npm --prefix apps/web run dev         # Frontend on :3000
```

In this mode, APISIX reaches services via `host.docker.internal:PORT`.

---

## Observability stack

The compose file defines an internal observability stack, gated behind the
`observability` Compose profile: `make third-party-up` and `make stack-up` never
start it. Start it with `make observability-up` and stop it with
`make observability-down`. Every host port is loopback-only.

| Service | Host port | Purpose |
| --- | --- | --- |
| `otel-collector` | `4318` | Receives OTLP traces and metrics from the services |
| `elasticsearch` | `9200` | Stores logs (shipped by the services) and traces (forwarded by the collector) |
| `kibana` | `5601` | Log and trace workspace |
| `prometheus` | `9090` | Stores scraped and pushed metrics |
| `grafana` | `3001` | Dashboards across all three pillars |

The stack is off by default in the sense that the services produce nothing
until `OTEL_ENABLED=true` and `LOG_OUTPUT=elasticsearch` are set; the containers
themselves start with the rest of the infrastructure. Elasticsearch security is
disabled for the single-node development cluster; a production deployment must
enable `xpack.security` and set credentials. The collector's backend routing
lives in `configs/otel-collector/config.yaml`; Prometheus scrape targets are
rendered from `configs/prometheus/prometheus.yml.template` by the
`prometheus-config` bootstrap so the service ports come from `configs/.env`
rather than being hardcoded.

## Docker verification

Before deploying, always run:

```sh
make docker-config     # Validate compose files
make docker-verify     # Validate + build images
```

`make docker-verify` validates the compose files and builds all application
images from `deploy/docker/docker-compose-dev.yml`, including the web image.

The web image is the one build that needs the configuration file: `next build`
validates the whole web configuration (the typed env module and
`next.config.js`) and inlines every `NEXT_PUBLIC_*` value into the browser
bundle. Both Compose files therefore hand `configs/.env` to that build as the
BuildKit secret `web_env`, which the Dockerfile mounts as `/app/.env` for the
build step only (nothing of it lands in a layer: the mount is not persisted,
and the copy `next build` makes in its standalone output is removed in the same
step), and pass the in-network gateway addresses as build args. Two consequences: a `docker build` outside
Compose needs `--secret id=web_env,src=configs/.env` plus those build args, and
the build step's cache key does not include the secret, so after changing a
`NEXT_PUBLIC_*` value rebuild the web image with `--no-cache`.

Application images use the `agentic-ai-platform/<service>:<tag>` format.
The default tag is `latest`. Set `APP_IMAGE_TAG` when you need a versioned
build or deploy:

```sh
make APP_IMAGE_TAG=0.1.0 docker-verify
make APP_IMAGE_TAG=0.1.0 prod-up
make APP_IMAGE_TAG=$(git rev-parse --short HEAD) docker-verify
```

### When to verify Docker

Run Docker verification when changing:
- `Dockerfile` in any service
- `compose.yaml` or `docker-compose-*.yml` in configs
- `pyproject.toml` or `uv.lock` (new dependencies)
- Import paths or package layout
- Files copied into Docker images

---

## Image build details

### Python services

All Python services use `uv` for dependency management and `hatchling` as build backend.

RAG uses the `src` Python package. Its Docker image copies that directory and
runs `python -m src`; the entrypoint reads `env.RAG_SERVICE_PORT`. Wheel package
paths and Alembic script lookup use `src/` too. The distribution name and the
database migration version table use the `rag-service` identifiers.

**Dockerfiles:**
- `apps/user-service/Dockerfile`
- `apps/rag-service/Dockerfile`
- `apps/tools-service/Dockerfile`
- `apps/agent-service/docker/Dockerfile.*`

**Build context:** The shared compose files use the repository root as the
build context. Dockerfile `COPY` paths must be relative to the repository root,
such as `apps/user-service/pyproject.toml`.

The root `.dockerignore` keeps generated files, dependency directories, local
environments, and repository metadata out of the shared build context. Keep it
updated when adding large generated directories or new service-local caches.

**Key image requirements:**
- Services with top-level imports like `models`, `schema`, `agents` must have those directories copied into the image (checked during `docker-verify`).
- Python service images remove `uv` and pip caches in the same build layers
  that install dependencies, so package caches don't ship in runtime images.
- The default agent-service image doesn't install Playwright Chromium. Set
  `OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED=true` only in an image/runtime that
  also installs the optional `browser` dependency group and browser binary.

### Web frontend

The web app uses **Next.js standalone output** (`output: "standalone"` in `next.config.js`). The Dockerfile is at `apps/web/Dockerfile`.
The shared compose files build it from the repository root, so package files are
copied from `apps/web/package.json`, `apps/web/package-lock.json`, and
`apps/web/lib/opal/package.json`.

Next.js imports server route modules during the image build. The web Dockerfile
therefore defines build-time defaults for `INTERNAL_URL`, `AGENT_SERVICE_URL`,
`USER_SERVICE_URL`, `RAG_SERVICE_URL`, and `TOOLS_SERVICE_URL`. Runtime compose
environment values or web env files can override those defaults.

---

## Startup order

```
1. PostgreSQL, Neo4j, Milvus, MinIO
       │
2. Keycloak (depends on PG)
       │
3. user-service (depends on PG, Keycloak)
       │
5. agent-service (depends on PG, user-service)
   rag-service (depends on PG, Milvus, Neo4j)
   tools-service (depends on PG, user-service)
       │
6. APISIX (depends on all services)
       │
7. Web frontend (depends on APISIX)
       │
8. Health check: curl http://localhost:8000/agent-service/health
```

---

## Environment configuration

### Files

| File | Purpose |
|------|---------|
| `configs/.env` | Single source of truth: infrastructure env vars (DB passwords, Keycloak config) and all service runtime config. Loaded by `config_manager` (`load_environment()`) and Docker Compose `env_file`. |

### Initialization

```sh
# Provide configs/.env and its credentials manually
make env-check  # Validate required keys
```

---

## Production deployment

```sh
# Validate config before deploy
make env-check
make docker-config

# Build and start production
docker compose --env-file configs/.env -f deploy/docker/docker-compose-prod.yml up -d
```

**Production differs from dev:**
- No hot-reload or volume mounts for source code
- Services use built images, not local source
- APISIX is configured for production upstreams
- Resource limits may be applied
- Set agent-service's pod `terminationGracePeriodSeconds` to at least
  `GRACEFUL_SHUTDOWN_TIMEOUT + CHAT_RUN_SHUTDOWN_GRACE_SECONDS +
  CHAT_RUN_CANCEL_GRACE_SECONDS + 10` (default `65`). Uvicorn first waits up
  to `GRACEFUL_SHUTDOWN_TIMEOUT` for open connections, and every chat stream
  stays open until its run ends, so live runs keep working during that wait.
  Only then does the lifespan give the remaining runs their shutdown grace,
  close them as `interrupted`, and close Redis. A shorter period lets SIGKILL
  cut that sequence off, and the reaper later closes those runs as
  `worker_lost`. `docker-compose-prod.yml` sets agent-service's `stop_grace_period`
  to `65s` for the same reason
- Chat-run event logs live in Redis for `CHAT_RUN_REPLAY_TTL_SECONDS`
  (default 10 minutes, at most `CHAT_RUN_MAX_EVENTS` frames per run, roughly
  7.5 MB for a worst-case run); monitor `used_memory`
- Alert on agent-service's `chat_run_heartbeat_lag_seconds` approaching
  `CHAT_RUN_LEASE_TTL_SECONDS` (blocking code on the event loop) and on
  `chat_runs_finished_total{reason="worker_lost"}` rising. Each replica holds
  up to about 150 chat-run Redis connections (writer 50, reader 100) on top of
  its shared pool; size Redis `maxclients` for the replica count

---

## Health checks

| Endpoint | Service | Expected response |
|----------|---------|------------------|
| `GET /api/v1/health` | user-service | `{"status": "healthy", "service": "user-service"}` |
| `GET /api/v1/health/ready` | user-service | DB readiness status |
| `GET /api/v1/health` | agent-service | `{"status": "ok"}` |
| `GET /api/v1/health` | rag-service | `{"status": "ok"}` |
| `GET /api/v1/graph/health` | rag-service (Neo4j) | `{"status": "ok", "service": "neo4j"}` |
| `GET /health` | tools-service | `{"status": "ok"}` |

Via APISIX:
```sh
curl http://localhost:8000/user-service/health
curl http://localhost:8000/user-service/health/ready
curl http://localhost:8000/user-service/api/v1/health
curl http://localhost:8000/user-service/api/v1/health/ready
curl http://localhost:8000/agent-service/health
curl http://localhost:8000/agent-service/api/v1/health
curl http://localhost:8000/rag-service/health
curl http://localhost:8000/rag-service/api/v1/health
curl http://localhost:8000/tools-service/health
```

---

## Rollback

This repository has no CI/CD pipeline. Rollback is manual:

```sh
# Revert to previous image tag or compose version
git checkout <previous-deploy-tag>
make docker-verify
docker compose -f deploy/docker/docker-compose-prod.yml up -d
```

---

## Pre-deployment checklist

- [ ] `make env-check` — all required env vars present
- [ ] `make validate` — all services pass lint + typecheck + test
- [ ] `make docker-verify` — compose config valid + images build
- [ ] `make quality-push` — pre-push quality gate passes
- [ ] `make docker-config` — deploy compose files are valid
- [ ] No `TODO` or `FIXME` in changed files
- [ ] Health checks pass after deployment
