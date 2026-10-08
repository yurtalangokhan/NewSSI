#!/usr/bin/env bash
# Auto-fix formatting and fixable lint in changed files; the pre-commit hook's
# only job. Quality gates (architecture, score, i18n, validate) live in check.sh.
#
# Usage: fix.sh [staged|push|all] [--strict]
#   staged    refuse partially staged targets, then re-stage what was fixed
#   push      fail when a fix changes a file, since the pushed commits lack it
#   --strict  fail when lint findings remain after fixing (check.sh uses this)
set -euo pipefail

MODE="staged"
STRICT=0

for arg in "$@"; do
  case "$arg" in
    staged | push | all) MODE="$arg" ;;
    --strict) STRICT=1 ;;
    *)
      echo "Usage: $0 [staged|push|all] [--strict]" >&2
      exit 2
      ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# shellcheck source=lib/changed_files.sh
source "$ROOT/scripts/quality/lib/changed_files.sh"

PYTHON_SERVICES=(agent-service rag-service user-service tools-service)
# Rag-service's application package lives in `src/` like the other services.
PYTHON_PATTERN='^apps/(agent-service|rag-service|user-service|tools-service)/(src|tests|alembic|migrations)/.*\.py$'
PRETTIER_PATTERN='^apps/web/(src|tests)/.*\.(ts|tsx|js|jsx|json|css|md)$'
ESLINT_PATTERN='^apps/web/(src|tests)/.*\.(ts|tsx|js|jsx)$'

# Existing files under $1 matching $2, relative to that directory.
files_under() {
  local prefix="$1"
  local pattern="$2"
  local file

  while IFS= read -r file; do
    [[ -f "$file" ]] && printf '%s\n' "${file#"$prefix"/}"
  done < <(grep -E "$pattern" <<<"$FILES" | grep -E "^$prefix/" || true)
}

fix_python_service() {
  local service="$1"
  local ruff_args=()
  local config_args=()
  local check_args=(--fix)

  mapfile -t ruff_args < <(files_under "apps/$service" "$PYTHON_PATTERN")
  ((${#ruff_args[@]} > 0)) || return 0

  # Every Python service carries the same base ruff.toml, so one explicit
  # config path covers all of them (no per-service special case).
  config_args=(--config ruff.toml)
  ((STRICT)) || check_args+=(--exit-zero)

  echo "==> $service: ruff format + ruff check --fix (${#ruff_args[@]} file(s))"
  (
    cd "apps/$service"
    uv run ruff format "${config_args[@]}" "${ruff_args[@]}"
    uv run ruff check "${config_args[@]}" "${check_args[@]}" "${ruff_args[@]}"
  )
}

fix_web() {
  local prettier_args=()
  local eslint_args=()
  local status=0

  mapfile -t prettier_args < <(files_under apps/web "$PRETTIER_PATTERN")
  mapfile -t eslint_args < <(files_under apps/web "$ESLINT_PATTERN")

  if ((${#prettier_args[@]} > 0)); then
    echo "==> web: prettier --write (${#prettier_args[@]} file(s))"
    (cd apps/web && npm exec -- prettier --write "${prettier_args[@]}")
  fi

  ((${#eslint_args[@]} > 0)) || return 0

  echo "==> web: eslint --fix (${#eslint_args[@]} file(s))"
  # The web config turns unused-import rules off for `make validate`; enable
  # the fixable one here so commits drop dead imports (as `lint:fix-unused`).
  (
    cd apps/web \
      && npm exec -- eslint --fix --quiet \
        --rule "unused-imports/no-unused-imports: error" "${eslint_args[@]}"
  ) || status=$?

  # ESLint exits 1 for remaining findings and 2 for crashes or bad config.
  if ((status == 1 && !STRICT)); then
    echo "web: eslint left unfixable findings; not blocking."
    return 0
  fi
  return "$status"
}

autofix_candidates() {
  grep -E "$PYTHON_PATTERN|$PRETTIER_PATTERN" <<<"$FILES" || true
}

ensure_candidates_fully_staged() {
  local partially_staged

  partially_staged="$(
    comm -12 \
      <(autofix_candidates | sort) \
      <(git diff --name-only --diff-filter=ACMR | sort)
  )"
  [[ -z "$partially_staged" ]] && return 0

  echo "Cannot auto-format partially staged files without also staging unstaged hunks." >&2
  echo "Stage or stash the unstaged changes in these files, then retry:" >&2
  printf '%s\n' "$partially_staged" | sed 's/^/ - /' >&2
  exit 1
}

restage_candidates() {
  local file

  while IFS= read -r file; do
    [[ -n "$file" && -e "$file" ]] && git add -f -- "$file"
  done < <(autofix_candidates)
}

# "<blob hash> <path>" per existing candidate, to detect what the fixes touched.
snapshot_candidates() {
  local paths=()

  mapfile -t paths < <(autofix_candidates | while IFS= read -r file; do
    [[ -f "$file" ]] && printf '%s\n' "$file"
  done)
  ((${#paths[@]} > 0)) || return 0

  paste -d ' ' \
    <(printf '%s\n' "${paths[@]}" | git hash-object --stdin-paths) \
    <(printf '%s\n' "${paths[@]}")
}

ensure_fixes_were_committed() {
  local before="$1"
  local changed

  changed="$(comm -13 <(sort <<<"$before") <(snapshot_candidates | sort) | cut -d ' ' -f 2-)"
  [[ -z "$changed" ]] && return 0

  echo "Auto-fix changed files the pushed commits don't include; commit the fixes, then push again:" >&2
  printf '%s\n' "$changed" | sed 's/^/ - /' >&2
  exit 1
}

FILES="$(quality_changed_files "$MODE" | sed '/^[[:space:]]*$/d')"

if [[ -z "$(autofix_candidates)" ]]; then
  echo "No auto-fixable files."
  exit 0
fi

[[ "$MODE" == "staged" ]] && ensure_candidates_fully_staged
[[ "$MODE" == "push" ]] && BEFORE_FIX="$(snapshot_candidates)"

for service in "${PYTHON_SERVICES[@]}"; do
  fix_python_service "$service"
done
fix_web

case "$MODE" in
  staged) restage_candidates ;;
  push) ensure_fixes_were_committed "$BEFORE_FIX" ;;
esac

echo "Auto-fix complete."
