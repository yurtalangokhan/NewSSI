# Deployment

## Deployment model

The platform is deployed as Docker containers orchestrated with Docker Compose. There is no Kubernetes or CI/CD pipeline configured (`.github/` is empty). All validation is local via Makefile quality gates.

---

## Connector tool upgrade

Apply agent-service migration `0046` before starting the updated application.
It adds an empty `connector_bindings` list to existing personas. Rebuild
tools-service to install its connector client dependencies, and refresh the
Kong configuration to include the internal connector-resolution route.

Both Compose environments provide the internal agent-service URL to
tools-service and the existing Airbyte config database settings to
agent-service. The initial credential resolver supports the configured Airbyte
0.50.x `NONE` secret persistence mode. It does not migrate or duplicate source
credentials. See [connector runtime variables](env-variables.md#saved-connector-runtime).

## Environments

### Local application with Docker Airbyte

The web app and Python services can run locally while Airbyte, PostgreSQL, and
Redis run in Docker. Start Airbyte from the repository root:

```powershell
docker volume create langgraph-with-ui_airbyte-workspace
docker volume create langgraph-with-ui_airbyte-data
docker compose --env-file configs/.env -f configs/docker-compose-services.yml up -d airbyte-server airbyte-worker airbyte-webapp
```

Before startup, create the database named by `AIRBYTE_DATABASE_URL` if it does
not exist. Set `AIRBYTE_DB_USER` and `AIRBYTE_DB_PASSWORD` to credentials accepted
by the existing PostgreSQL instance. Changing a container environment variable
does not change the password stored in an existing PostgreSQL volume.

For the pinned Temporal image, set `AIRBYTE_DYNAMIC_CONFIG_FILE_PATH` to
`config/dynamicconfig/docker.yaml`, which is bundled in the image. The worker
requires its `control-plane` environment and the actual external workspace
volume name; Compose supplies both. The webapp's unused Community Keycloak
upstream uses the image's `localhost` placeholder.

The bootloader should exit with code zero; server and Temporal should be healthy,
and worker/webapp should remain running. The configured local UI is
`http://localhost:8010`; API health is `http://localhost:8001/api/v1/health`.
Local agent-service uses `AIRBYTE_API_URL=http://localhost:8001/api/v1`.
Connector jobs reach the Docker PostgreSQL service at `postgres:5432`.

| Environment | Compose file | Purpose |
|-------------|-------------|---------|
| Development | `configs/docker-compose-dev.yml` | Local dev with hot-reload |
| Production | `configs/docker-compose-prod.yml` | Production deployment |

---

## Local deployment

### Prerequisites

- Docker + Docker Compose
- A working NVIDIA GPU driver (`nvidia-smi`) and NVIDIA Container Toolkit for
  the Compose-managed Ollama service
- An existing external Docker volume named `ollama` for Ollama model data
- Python 3.11+ with `uv` installed
- Node.js 20+ (for frontend)
- At least 8GB RAM, 20GB disk

### Step-by-step

```sh
# 1. Clone and prepare env files
make env-init
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

In this mode, Kong reaches services via `host.docker.internal:PORT`.

---

## Docker verification

Before deploying, always run:

```sh
make docker-config     # Validate compose files
make docker-verify     # Validate + build images
```

`make docker-verify` validates the compose files and builds all application
images from `configs/docker-compose-dev.yml`, including the web image.

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
`USER_SERVICE_URL`, `LANGCONNECT_URL`, and `TOOLS_SERVICE_URL`. Runtime compose
environment values or web env files can override those defaults.

---

## Startup order

```
1. PostgreSQL, Neo4j, Milvus, MinIO
       │
2. Keycloak (depends on PG)
       │
3. Airbyte (depends on PG, MinIO)
       │
4. user-service (depends on PG, Keycloak)
       │
5. agent-service (depends on PG, user-service)
   rag-service (depends on PG, Milvus, Neo4j)
   tools-service (depends on PG, user-service)
       │
6. Kong (depends on all services)
       │
7. Web frontend (depends on Kong)
       │
8. Health check: curl http://localhost:8000/agent-service/health
```

---

## Environment configuration

### Files

| File | Purpose |
|------|---------|
| `configs/.env` | Infrastructure env vars (DB passwords, Keycloak config, Airbyte config) |
| `apps/user-service/.env` | User service runtime config |
| `apps/agent-service/.env` | Agent service runtime config |
| `apps/rag-service/.env` | RAG service runtime config |
| `apps/tools-service/.env` | Tools service runtime config |
| `apps/web/.env` | Web frontend runtime config |

### Initialization

```sh
make env-init   # Creates missing .env files from templates
make env-check  # Validates all .env files have required keys
```

---

## Production deployment

```sh
# Validate config before deploy
make env-check
make docker-config

# Build and start production
docker compose --env-file configs/.env -f configs/docker-compose-prod.yml up -d
```

**Production differs from dev:**
- No hot-reload or volume mounts for source code
- Services use built images, not local source
- Kong is configured for production upstreams
- Resource limits may be applied

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

Via Kong:
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
docker compose -f configs/docker-compose-prod.yml up -d
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
