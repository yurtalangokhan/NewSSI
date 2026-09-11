#!/usr/bin/env bash
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"

if [[ -v QUALITY_FILES ]]; then
  FILES="$QUALITY_FILES"
elif (($# == 2)); then
  FILES="$(git diff --name-only --diff-filter=ACMRTD "$1...$2")"
  status=$?
  if ((status != 0)); then
    echo "Unable to determine changed files for $1...$2." >&2
    exit "$status"
  fi
else
  echo "Usage: $0 <base-revision> <head-revision>" >&2
  exit 2
fi

FILES="$(printf '%s\n' "$FILES" | sed '/^[[:space:]]*$/d')"

service_has_relevant_changes() {
  local service="$1"
  local relative_path

  while IFS= read -r relative_path; do
    relative_path="${relative_path#apps/$service/}"

    case "$relative_path" in
      src/* | tests/* | models/* | schema/* | alembic/* | migrations/* | docker/*)
        return 0
        ;;
      Makefile | Dockerfile | compose.yml | compose.yaml | pyproject.toml | uv.lock | ruff.toml | mypy.ini | pytest.ini)
        return 0
        ;;
    esac

    if [[ "$service" == "web" ]]; then
      case "$relative_path" in
        package.json | package-lock.json | next.config.* | tsconfig*.json | jest.config.* | playwright.config.* | eslint.config.* | .eslintrc* | .prettier*)
          return 0
          ;;
      esac
    fi
  done < <(printf '%s\n' "$FILES" | grep -E "^apps/$service/" || true)

  return 1
}

services=(agent-service rag-service user-service tools-service web)
selected_services=()

for service in "${services[@]}"; do
  if service_has_relevant_changes "$service"; then
    selected_services+=("$service")
  fi
done

if ((${#selected_services[@]} == 0)); then
  printf '[PASS] merge:no-service-changes\n'
  exit 0
fi

status=0
for service in "${selected_services[@]}"; do
  if ! "$ROOT/scripts/validation/quiet-run.sh" "validate:$service" -- \
    make -C "$ROOT/apps/$service" validate; then
    status=1
  fi
done

exit "$status"
