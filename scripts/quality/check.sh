#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-staged}"
ROOT="$(git rev-parse --show-toplevel)"
STEP=0

cd "$ROOT"

# shellcheck source=lib/changed_files.sh
source "$ROOT/scripts/quality/lib/changed_files.sh"
# shellcheck source=lib/docker_services.sh
source "$ROOT/scripts/quality/lib/docker_services.sh"

if [[ -t 1 ]]; then
  BOLD="$(tput bold 2>/dev/null || true)"
  DIM="$(tput dim 2>/dev/null || true)"
  GREEN="$(tput setaf 2 2>/dev/null || true)"
  RED="$(tput setaf 1 2>/dev/null || true)"
  CYAN="$(tput setaf 6 2>/dev/null || true)"
  RESET="$(tput sgr0 2>/dev/null || true)"
else
  BOLD=""
  DIM=""
  GREEN=""
  RED=""
  CYAN=""
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

has_changed_path() {
  local pattern="$1"
  grep -Eq "$pattern" <<<"$FILES"
}

run_python_service_checks() {
  local service="$1"
  run "$service validate" make -C "apps/$service" validate
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

FILES="$(quality_changed_files "$MODE" | sed '/^[[:space:]]*$/d')"

if [[ -z "$FILES" ]]; then
  echo "No changed files for quality gate."
  exit 0
fi

print_file_summary

run "shell syntax check" bash -n \
  scripts/git-hooks/pre-commit \
  scripts/git-hooks/pre-push \
  scripts/install-git-hooks.sh \
  scripts/validate-commit.sh \
  scripts/validate-merge.sh \
  scripts/validate-push.sh \
  scripts/validate-spec.sh \
  scripts/validate-task.sh \
  scripts/validation/quiet-run.sh \
  scripts/quality/check.sh \
  scripts/quality/fix.sh \
  scripts/quality/lib/changed_files.sh \
  scripts/quality/lib/docker_services.sh

run "autofix" bash scripts/quality/fix.sh "$MODE" --strict

if [[ "$MODE" == "staged" ]]; then
  run "staged whitespace check" git diff --cached --check
fi

if [[ "$MODE" != "staged" ]]; then
  for service in agent-service rag-service user-service tools-service; do
    if has_changed_path "^apps/$service/(src|tests|alembic|migrations|pyproject.toml|uv.lock|Makefile)"; then
      run_python_service_checks "$service"
    fi
  done
fi

# Shared packages: ruff on every changed package file, mypy on the packages
# this gate enforces (see Makefile packages-typecheck for the split between
# enforced and report-only packages).
if has_changed_path '^packages/[^/]+/(src|tests)/.*\.py$'; then
  run "packages lint" make packages-lint
  run "packages typecheck" make packages-typecheck
fi

if has_changed_path '^(apps/(agent-service|rag-service|user-service|tools-service)/|packages/localization/|scripts/quality/check_localization.py)'; then
  # check_localization.py imports the i18n package, whose only declared dependency is
  # starlette; that is only guaranteed to be installed in localization's own venv,
  # not whatever `python3` happens to resolve to on the caller's PATH.
  run "backend i18n check" packages/localization/.venv/bin/python3 scripts/quality/check_localization.py
fi

# Architecture & code-quality gate (blocking). Enforces docs/oop-solid-architecture.md
# and the "Architecture & code-quality gate" section of docs/coding-standards.md.
# Runs on push and quality-staged; pre-existing offenders do not block unless they are part
# of the current diff (changed-files-only policy).
if has_changed_path '^(apps/(agent-service|rag-service|user-service|tools-service)/|apps/web/)'; then
  # In "all" mode the file list is the whole repository, which exceeds the
  # kernel's per-variable limit (MAX_ARG_STRLEN, 128 KB) and makes every later
  # exec fail with E2BIG. The Python side resolves the same list from
  # QUALITY_MODE, so hand it the mode instead of the list.
  if [[ "$MODE" == "all" ]]; then
    export QUALITY_MODE="all"
    unset QUALITY_FILES
  else
    export QUALITY_FILES="$FILES"
  fi
  run "architecture & code-quality gate" python3 scripts/quality/check_architecture.py --changed
  if [[ "$MODE" == "all" ]]; then
    run "quality score report" python3 scripts/quality/score.py --changed
  else
    run "quality score threshold" python3 scripts/quality/score.py --changed --min-score "${QUALITY_SCORE_MIN:-80}"
  fi
fi


if [[ "$MODE" != "staged" ]] && has_changed_path '^apps/web/(src|tests|package.json|package-lock.json|Makefile|next.config|tsconfig|jest.config|playwright.config)'; then
  run "web validate" run_web_checks
fi

if [[ "$MODE" != "staged" ]] && has_changed_path '^(deploy/docker/docker-compose.*\.ya?ml|configs/docker-compose.*\.ya?ml|docker-compose.*\.ya?ml|apps/.*/compose\.ya?ml|apps/.*/Dockerfile|apps/.*/docker/Dockerfile.*|apps/.*/pyproject\.toml|apps/.*/uv\.lock|apps/.*/package(-lock)?\.json|Makefile)'; then
  run "docker compose config" make docker-config
fi

if [[ "$MODE" != "staged" ]]; then
  DOCKER_SERVICES="$(quality_docker_services <<<"$FILES")" || {
    printf '%s[FAIL]%s docker build scope\n' "$RED" "$RESET" >&2
    exit 1
  }
  if [[ -n "$DOCKER_SERVICES" ]]; then
    run "docker image build ($DOCKER_SERVICES)" make docker-build-services PYTHON_SERVICES="$DOCKER_SERVICES"
    if grep -qw 'agent-service' <<<"$DOCKER_SERVICES"; then
      run "agent-service docker import smoke" make docker-smoke-agent-service
    fi
  fi
fi

printf '\n%sQuality gate passed.%s %s%d step(s) completed.%s\n' "$GREEN" "$RESET" "$DIM" "$STEP" "$RESET"
