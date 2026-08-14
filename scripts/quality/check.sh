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

run_python_service_fixes() {
  local service="$1"
  local ruff_args=()
  local file

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    ruff_args+=("${file#apps/$service/}")
  done < <(grep -E "^apps/$service/(src|tests|alembic|migrations)/.*\.py$" <<<"$FILES" || true)

  ((${#ruff_args[@]} > 0)) || return 0

  if [[ "$service" == "agent-service" ]]; then
    (
      cd "apps/$service"
      uv run ruff format --config ruff.toml "${ruff_args[@]}"
      uv run ruff check --config ruff.toml --fix "${ruff_args[@]}"
    )
    return
  fi

  (
    cd "apps/$service"
    uv run ruff format "${ruff_args[@]}"
    uv run ruff check --fix "${ruff_args[@]}"
  )
}

run_web_fixes() {
  local eslint_args=()
  local prettier_args=()
  local file

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    prettier_args+=("${file#apps/web/}")
  done < <(grep -E '^apps/web/(src|tests)/.*\.(ts|tsx|js|jsx|json|css|md)$' <<<"$FILES" || true)

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    eslint_args+=("${file#apps/web/}")
  done < <(grep -E '^apps/web/(src|tests)/.*\.(ts|tsx|js|jsx)$' <<<"$FILES" || true)

  ((${#prettier_args[@]} > 0 || ${#eslint_args[@]} > 0)) || return 0

  (
    cd apps/web
    if ((${#prettier_args[@]} > 0)); then
      npm exec -- prettier --write "${prettier_args[@]}"
    fi
    if ((${#eslint_args[@]} > 0)); then
      npm exec -- eslint --fix --quiet "${eslint_args[@]}"
    fi
  )
}

autofix_candidate_files() {
  grep -E '^(apps/(agent-service|rag-service|user-service|tools-service)/(src|tests|alembic|migrations)/.*\.py|apps/web/(src|tests)/.*\.(ts|tsx|js|jsx|json|css|md))$' <<<"$FILES" || true
}

ensure_staged_files_can_be_refreshed() {
  local partially_staged
  local candidates

  [[ "$MODE" == "staged" ]] || return 0

  candidates="$(autofix_candidate_files)"
  [[ -n "$candidates" ]] || return 0

  partially_staged="$(
    comm -12 \
      <(printf '%s\n' "$candidates" | sort) \
      <(git diff --name-only --diff-filter=ACMR | sort)
  )"

  if [[ -n "$partially_staged" ]]; then
    printf '%s[FAIL]%s Cannot auto-format partially staged files without also staging unstaged hunks.%s\n' "$RED" "$RESET" "$RESET" >&2
    printf '%sStage or stash the unstaged changes in these files, then retry:%s\n' "$YELLOW" "$RESET" >&2
    printf '%s\n' "$partially_staged" | sed 's/^/ - /' >&2
    exit 1
  fi
}

refresh_staged_files() {
  local file
  local candidates

  [[ "$MODE" == "staged" ]] || return 0

  candidates="$(autofix_candidate_files)"
  [[ -n "$candidates" ]] || return 0

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    [[ -e "$file" ]] && git add -- "$file"
  done <<<"$candidates"
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
  make -C apps/web validate
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

run "shell syntax check" bash -n \
  scripts/git-hooks/pre-commit \
  scripts/git-hooks/pre-push \
  scripts/install-git-hooks.sh \
  scripts/quality/check.sh

ensure_staged_files_can_be_refreshed

for service in agent-service rag-service user-service tools-service; do
  if has_changed_path "^apps/$service/(src|tests|alembic|migrations|pyproject.toml|uv.lock|Makefile)"; then
    run "$service autofix" run_python_service_fixes "$service"
  fi
done

if has_changed_path '^apps/web/(src|tests|package.json|package-lock.json|next.config|tsconfig|jest.config|playwright.config)'; then
  run "web autofix" run_web_fixes
fi

refresh_staged_files

if [[ "$MODE" == "staged" ]]; then
  run "staged whitespace check" git diff --cached --check
fi

for service in agent-service rag-service user-service tools-service; do
  if has_changed_path "^apps/$service/(src|tests|alembic|migrations|pyproject.toml|uv.lock|Makefile)"; then
    run_python_service_checks "$service"
  fi
done

if has_changed_path '^(apps/(agent-service|rag-service|user-service|tools-service)/|packages/i18n-py/|scripts/quality/check_i18n.py)'; then
  run "backend i18n check" python3 scripts/quality/check_i18n.py
fi


if has_changed_path '^apps/web/(src|tests|package.json|package-lock.json|Makefile|next.config|tsconfig|jest.config|playwright.config)'; then
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
