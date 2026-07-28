#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ENV_FILE="${OLLAMA_ENV_FILE:-$ROOT/configs/.env}"
COMPOSE_FILE="${OLLAMA_COMPOSE_FILE:-$ROOT/configs/docker-compose-services.yml}"
SERVICE_NAME="${OLLAMA_SERVICE_NAME:-ollama}"
DEFAULT_MODELS="llama3.1:8b nomic-embed-text"

read_env_value() {
  local key="$1"
  local file="$2"

  awk -v key="$key" '
    /^[[:space:]]*($|#)/ { next }
    {
      split($0, parts, "=")
      name = parts[1]
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
      if (name == key) {
        value = substr($0, index($0, "=") + 1)
        sub(/\r$/, "", value)
        print value
        exit
      }
    }
  ' "$file"
}

MODELS="${OLLAMA_PRELOAD_MODELS:-}"
if [[ -z "$MODELS" && -f "$ENV_FILE" ]]; then
  MODELS="$(read_env_value "OLLAMA_PRELOAD_MODELS" "$ENV_FILE")"
fi
MODELS="${MODELS:-$DEFAULT_MODELS}"

if [[ -z "${MODELS// }" ]]; then
  echo "No Ollama models configured in OLLAMA_PRELOAD_MODELS."
  exit 0
fi

cd "$ROOT"

echo "Waiting for Ollama service to become healthy..."
for _ in $(seq 1 60); do
  if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" ollama list >/dev/null 2>&1; then
  echo "Ollama service is not ready. Start it first with:" >&2
  echo "make third-party-up" >&2
  exit 1
fi

for model in $MODELS; do
  echo "Pulling Ollama model: $model"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" ollama pull "$model"
done
