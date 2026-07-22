#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-staged}"
ROOT="$(git rev-parse --show-toplevel)"
STEP=0

cd "$ROOT"

if [[ -t 1 ]]; then
  BOLD="$(tput bold 2>/dev/null || true)"
  DIM="$(tput dim 2>/dev/null || true)"
  GREEN="$(tput setaf 2 2>/dev/null || true)"
  RED="$(tput setaf 1 2>/dev/null || true)"
  CYAN="$(tput setaf 6 2>/dev/null || true)"
  YELLOW="$(tput setaf 3 2>/dev/null || true)"
  RESET="$(tput sgr0 2>/dev/null || true)"
else
  BOLD=""
  DIM=""
  GREEN=""
  RED=""
  CYAN=""
  YELLOW=""
  RESET=""
fi

log() {
  printf '\n%s==> %s%s\n' "$CYAN" "$*" "$RESET"
}

run() {
  local label="$1"
  shift
  local started
  local elapsed

  STEP=$((STEP + 1))
  started="$(date +%s)"
  printf '\n%s[%02d] %s%s\n' "$BOLD" "$STEP" "$label" "$RESET"
  printf '%s$ %s%s\n' "$DIM" "$*" "$RESET"

  if "$@"; then
    elapsed=$(($(date +%s) - started))
    printf '%s[OK]%s %s (%ss)\n' "$GREEN" "$RESET" "$label" "$elapsed"
  else
    elapsed=$(($(date +%s) - started))
    printf '%s[FAIL]%s %s (%ss)\n' "$RED" "$RESET" "$label" "$elapsed" >&2
    exit 1
  fi
}

changed_files() {
  if [[ -n "${QUALITY_FILES:-}" ]]; then
    printf '%s\n' "$QUALITY_FILES"
    return
  fi

  case "$MODE" in
    staged)
      git diff --cached --name-only --diff-filter=ACMR
      ;;
    push)
      if git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
        git diff --name-only --diff-filter=ACMR '@{upstream}...HEAD'
      else
        git diff --name-only --diff-filter=ACMR HEAD~1...HEAD 2>/dev/null \
          || git diff --name-only --diff-filter=ACMR HEAD
      fi
      ;;
    all)
      git ls-files
      ;;
    *)
      echo "Unknown quality mode: $MODE" >&2
      exit 2
      ;;
  esac
}

has_changed_path() {
  local pattern="$1"
  grep -Eq "$pattern" <<<"$FILES"
}

run_python_service_checks() {
  local service="$1"
  run "$service validate" make -C "apps/$service" validate
}

changed_docker_services() {
  local service
  local services=()

  if has_changed_path '^(configs/docker-compose.*\.ya?ml|docker-compose.*\.ya?ml|Makefile|scripts/)'; then
    printf '%s\n' "agent-service user-service rag-service tools-service"
    return
  fi

  for service in agent-service rag-service user-service tools-service; do
    if has_changed_path "^apps/$service/(src|models|schema|tests|alembic|migrations|pyproject.toml|uv.lock|Makefile|Dockerfile|docker/Dockerfile.*|compose\.ya?ml)"; then
      services+=("$service")
    fi
  done

  printf '%s\n' "${services[*]}"
}

run_web_checks() {
  log "web validate"
  (
    cd apps/web
    npm run lint
    npm run types:check
    npm run test:ci
  )
}

print_file_summary() {
  local count
  local limit=40
  count="$(printf '%s\n' "$FILES" | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"

  log "Quality gate mode: $MODE"
  printf '%sFiles considered:%s %s\n' "$BOLD" "$RESET" "$count"

  if [[ "$MODE" == "all" ]]; then
    printf '%sFull repository scan selected; file list suppressed for readability.%s\n' "$DIM" "$RESET"
    return
  fi

  printf '%sChanged files:%s\n' "$BOLD" "$RESET"
  printf '%s\n' "$FILES" | sed -n "1,${limit}p" | sed 's/^/ - /'
  if ((count > limit)); then
    printf '%s... and %d more file(s).%s\n' "$DIM" "$((count - limit))" "$RESET"
  fi
}

FILES="$(changed_files | sed '/^[[:space:]]*$/d')"

if [[ -z "$FILES" ]]; then
  echo "No changed files for quality gate."
  exit 0
fi

print_file_summary

if [[ "$MODE" == "staged" ]]; then
  run "staged whitespace check" git diff --cached --check
fi

run "shell syntax check" bash -n \
  scripts/git-hooks/pre-commit \
  scripts/git-hooks/pre-push \
  scripts/install-git-hooks.sh \
  scripts/quality/check.sh

for service in agent-service rag-service user-service tools-service; do
  if has_changed_path "^apps/$service/(src|tests|alembic|migrations|pyproject.toml|uv.lock|Makefile)"; then
    run_python_service_checks "$service"
  fi
done

if has_changed_path '^apps/web/(src|tests|package.json|package-lock.json|next.config|tsconfig|jest.config|playwright.config)'; then
  run "web validate" run_web_checks
fi

if has_changed_path '^(configs/docker-compose.*\.ya?ml|docker-compose.*\.ya?ml|apps/.*/compose\.ya?ml|apps/.*/Dockerfile|apps/.*/docker/Dockerfile.*|apps/.*/pyproject\.toml|apps/.*/uv\.lock|apps/.*/package(-lock)?\.json|Makefile|scripts/)'; then
  run "docker compose config" make docker-config
fi

DOCKER_SERVICES="$(changed_docker_services)"
if [[ -n "$DOCKER_SERVICES" ]] && has_changed_path '^(configs/docker-compose.*\.ya?ml|docker-compose.*\.ya?ml|apps/.*/compose\.ya?ml|apps/.*/Dockerfile|apps/.*/docker/Dockerfile.*|apps/.*/pyproject\.toml|apps/.*/uv\.lock|apps/(agent-service|rag-service|user-service|tools-service)/(src|models|schema|tests|alembic|migrations|Makefile)|Makefile|scripts/)'; then
  run "docker image build ($DOCKER_SERVICES)" make docker-build-services PYTHON_SERVICES="$DOCKER_SERVICES"
fi

printf '\n%sQuality gate passed.%s %s%d step(s) completed.%s\n' "$GREEN" "$RESET" "$DIM" "$STEP" "$RESET"
