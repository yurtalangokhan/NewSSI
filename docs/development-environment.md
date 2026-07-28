# Development Environment

This runbook documents how local agents and developers should prepare env files
and start the platform. The project intentionally separates infrastructure env
from app runtime env.

## Env Ownership

- `configs/.env` is only for third-party service compose:
  `configs/docker-compose-services.yml`, Kong rendering, Keycloak bootstrap,
  Postgres, Neo4j, Airbyte, Milvus, and MinIO.
- `apps/web/.env` is the web runtime env.
- `apps/agent-service/.env`, `apps/rag-service/.env`,
  `apps/user-service/.env`, and `apps/tools-service/.env` are service runtime
  env files.
- `.vscode/launch.json` uses the app env files directly for host-based local
  development.
- `configs/docker-compose-dev.yml` also reads the app env files, then overrides
  host-only gateway URLs to Docker-network URLs such as `http://kong:8000`.

Do not commit real `.env` files. They are ignored because they can contain
service client secrets. Use the env manager script to create or validate them.

## Env Commands

From the repository root:

```sh
make env-init
make env-check
make env-test
```

`make env-init` creates missing env files and appends missing keys with an
inline description and a safe development default when one exists.

`make env-check` reports:

- missing required keys
- required keys that are present but empty
- extra keys that are not part of the architecture

When a required secret is empty, fill it from the target environment or run the
Keycloak bootstrap flow that writes service client secrets.

## Traffic Rules

All external HTTP traffic goes through Kong on port `8000`.

For VS Code or host-based service launches:

- Web calls `http://localhost:8000`.
- Services call internal Kong routes such as
  `http://localhost:8000/internal/user-service`.
- Kong reaches host services through `host.docker.internal` upstreams from
  `configs/.env`.

For Docker Compose app services:

- App containers still read `apps/*/.env`.
- `configs/docker-compose-dev.yml` overrides gateway URLs to
  `http://kong:8000`.
- Backend service ports are published so Kong's host upstreams can still reach
  them when the app stack is containerized.

## Start Order

1. Prepare env files:

   ```sh
   make env-init
   make env-check
   ```

2. Start the full Docker stack:

   ```sh
   make stack-up
   ```

   This target starts the third-party services from
   `configs/docker-compose-services.yml`, runs
   `scripts/pull_ollama_models.sh`, and then starts the application
   microservices from `configs/docker-compose-prod.yml`.

   `scripts/pull_ollama_models.sh` reads `OLLAMA_PRELOAD_MODELS` from
   `configs/.env` and pulls those models through the existing `ollama` compose
   service. It doesn't start a separate model-pull container.

3. Optional: start only one layer:

   ```sh
   make third-party-up
   make ollama-models
   make prod-up
   ```

   Use this split flow when you need to inspect the third-party services before
   starting the application microservices. For host-based development, start
   services from `.vscode/launch.json`; the launch configs read the same app env
   files.

4. Validate compose rendering and image builds after env or compose changes:

   ```sh
   make docker-config
   make docker-verify
   ```

## Health Checks

Kong-routed checks:

```sh
curl http://localhost:8000/health/
curl http://localhost:8000/api/health
curl http://localhost:8000/api/rag/health
```

Direct service ports are useful only for debugging a single service. The app
architecture should prefer Kong-routed URLs.
