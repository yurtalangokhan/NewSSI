# Deployment

## Deployment model

The platform is deployed as Docker containers orchestrated with Docker Compose. There is no Kubernetes or CI/CD pipeline configured (`.github/` is empty). All validation is local via Makefile quality gates.

---

## Environments

| Environment | Compose file | Purpose |
|-------------|-------------|---------|
| Development | `configs/docker-compose-dev.yml` | Local dev with hot-reload |
| Production | `configs/docker-compose-prod.yml` | Production deployment |

---

## Local deployment

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ with `uv` installed
- Node.js 20+ (for frontend)
- At least 8GB RAM, 20GB disk

### Step-by-step

```sh
# 1. Clone and prepare env files
make env-init
make env-check

# 2. Start infrastructure (Postgres, Neo4j, Milvus, Airbyte, Keycloak)
docker compose --env-file configs/.env -f configs/docker-compose-services.yml up -d

# 3. Start app services
docker compose --env-file configs/.env -f configs/docker-compose-dev.yml up -d

# 4. Verify everything is running
curl http://localhost:8000/health/
curl http://localhost:8000/api/health
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

`make docker-verify` builds all Python service images from `configs/docker-compose-dev.yml`.

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

**Build context:** Each service's `apps/<service>/` directory.

**Key image requirements:**
- Services with top-level imports like `models`, `schema`, `agents` must have those directories copied into the image (checked during `docker-verify`).

### Web frontend

The web app uses **Next.js standalone output** (`output: "standalone"` in `next.config.js`). The Dockerfile is at `apps/web/Dockerfile`.

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
8. Health check: curl http://localhost:8000/health/
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
| `GET /health/` | user-service | `{"status": "healthy", "service": "user-service"}` |
| `GET /health` | agent-service | `{"status": "ok"}` |
| `GET /health` | rag-service | `{"status": "ok"}` |
| `GET /graph/health` | rag-service (Neo4j) | `{"status": "ok", "service": "neo4j"}` |
| `GET /health/ready` | user-service | `{"status": "ready", ...}` (with DB ping) |

Via Kong:
```sh
curl http://localhost:8000/health/
curl http://localhost:8000/api/health
curl http://localhost:8000/api/rag/health
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
