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

Direct service ports are useful only for debugging a single service. The app
architecture should prefer Kong-routed URLs.

## Ollama GPU operations

Ollama is an infrastructure Compose service. It reuses the external Docker
volume named `ollama` for model data and reserves all available NVIDIA GPUs for
that service only. Start and manage it through the repository Compose commands,
not a host `ollama serve` process.

### Prerequisites

Before starting the infrastructure stack, confirm that the host GPU driver and
the Docker GPU integration are available and that the existing model-data
volume is present. First, derive the published port from `configs/.env`. The
command uses `11434` only when `OLLAMA_PORT` is absent or empty, and it rejects
non-numeric or out-of-range values.

```sh
OLLAMA_PORT="$(
  awk -F= '
    $1 ~ /^[[:space:]]*OLLAMA_PORT[[:space:]]*$/ {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]\r]+$/, "", value)
      print value
      exit
    }
  ' configs/.env
)"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
case "$OLLAMA_PORT" in
  *[!0-9]*) echo "Invalid OLLAMA_PORT" >&2; false ;;
esac
[ "$OLLAMA_PORT" -ge 1 ] && [ "$OLLAMA_PORT" -le 65535 ]

nvidia-smi
docker run --rm --gpus all ubuntu nvidia-smi
docker volume inspect ollama
```

Do not continue if the port validation fails. The first `nvidia-smi` command
must report the host GPU, and the temporary Docker probe must report the same
GPU through the NVIDIA Container Toolkit. The probe may pull the `ubuntu` image
the first time it runs, but it doesn't mount the Ollama volume. The `ollama`
volume must already exist. Compose treats it as external and does not create
it.

<!-- prettier-ignore -->
> [!WARNING]
> Never run `docker compose down -v`, `docker rm -v`, or another
> volume-removal command for Ollama. The external `ollama` volume contains the
> model data that Compose reuses.

### Start and update models

Use the Makefile targets from the repository root. They use
`configs/docker-compose-services.yml` with `configs/.env`.

```sh
make third-party-up
make ollama-models
```

`make third-party-up` starts the Compose-managed infrastructure, including
Ollama. `make ollama-models` runs the existing model-pull script against that
service. `make stack-up` performs those two steps and then starts the
application services.

### One-time handover

Use this procedure only when a standalone `ollama` container or a host listener
currently owns the Ollama name or port. Do not stop or remove anything until
you confirm the existing container's identity and model-data mount.

1. Confirm that the external volume exists and inspect any container named
   `ollama`.

   ```sh
   docker volume inspect ollama
   docker ps -a --filter 'name=^/ollama$'
   docker inspect ollama --format '{{json .Config.Labels}}'
   docker inspect ollama --format '{{json .Mounts}}'
   ```

   Inspect the project label `com.docker.compose.project` and service label
   `com.docker.compose.service`. If they already equal
   `agentic-ai-infrastructure` and `ollama`, respectively, the container is
   Compose-managed: do not stop or remove it. Continue with removal only for a
   standalone container whose mount object has the name `ollama`, destination
   `/root/.ollama`, and `RW` set to `true`.

2. Check whether a host process owns the published Ollama port.

   ```sh
   sudo ss -ltnp "sport = :$OLLAMA_PORT"
   ```

   If a verified host `ollama serve` listener owns the port, stop it from its
   original terminal or service manager. For a system service, use:

   ```sh
   sudo systemctl stop ollama
   ```

   Do not use broad process-kill commands. If the port owner is unclear, stop
   the handover and identify it before continuing.

3. Reconfirm GPU access immediately before any destructive handover.

   ```sh
   nvidia-smi
   docker run --rm --gpus all ubuntu nvidia-smi
   ```

   Both commands must succeed. If either fails, do not stop or remove the
   existing container.

4. If the inspected container is standalone and has the exact required mount,
   stop and remove only that container. Do not add volume-removal flags.

   ```sh
   docker stop ollama
   docker rm ollama
   ```

5. Start the Compose service and pull configured models when needed.

   ```sh
   make third-party-up
   make ollama-models
   ```

### Verify Compose ownership and GPU use

After startup, run the following checks. The labels must identify project
`agentic-ai-infrastructure` and service `ollama`; the mount must identify
volume `ollama`, destination `/root/.ollama`, and `RW` as `true`; and the
health status must be `healthy`.

```sh
docker inspect ollama --format '{{json .Config.Labels}}'
docker inspect ollama --format '{{json .Mounts}}'
docker inspect ollama --format '{{.State.Health.Status}}'
docker exec ollama ollama list
docker inspect ollama --format '{{json .HostConfig.DeviceRequests}}'
curl --fail --silent --show-error \
  "http://localhost:$OLLAMA_PORT/api/generate" \
  -H 'Content-Type: application/json' \
  -d '{"model":"llama3.1:8b","prompt":"Reply with OK.","stream":false}'
docker exec ollama ollama ps
```

The device-request output must include the `nvidia` driver and the `gpu`
capability. Docker renders Compose's `count: all` GPU reservation as a device
request with a count of `-1`. `ollama list` shows the models available in the
reused volume. The API call performs a noninteractive generation request with
the existing default generation model, `llama3.1:8b`, before checking runtime
placement. After the request succeeds, `ollama ps` must show `llama3.1:8b`
with `100% GPU` to prove live GPU placement.

### Troubleshoot Ollama startup

Use these checks to resolve common startup failures without risking model data.

- **Port or name conflict:** Check `docker ps -a --filter 'name=^/ollama$'`
  and `sudo ss -ltnp "sport = :$OLLAMA_PORT"`. Follow the one-time handover only
  after verifying the current container mount or host listener identity.
- **Missing external volume:** `docker volume inspect ollama` fails when the
  required volume is absent. Do not create a new empty volume in its place;
  recover the original volume or obtain the correct volume from its owner.
- **Unavailable NVIDIA driver:** If `nvidia-smi` fails or Docker does not grant
  the NVIDIA device request, install or repair the host NVIDIA driver and
  NVIDIA Container Toolkit before restarting the Compose service.
