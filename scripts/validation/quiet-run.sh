#!/usr/bin/env bash
set -uo pipefail

if (($# < 3)) || [[ "$2" != "--" ]]; then
  echo "Usage: $0 <label> -- <command> [args...]" >&2
  exit 2
fi

LABEL="$1"
shift 2

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG_DIR="${VALIDATION_LOG_DIR:-$ROOT/.tmp/validation}"
SAFE_LABEL="$(printf '%s' "$LABEL" | sed 's/[^[:alnum:]_.-]/-/g')"

mkdir -p "$LOG_DIR"
LOG_FILE="$(mktemp "$LOG_DIR/${SAFE_LABEL}.XXXXXX.log")"

if "$@" >"$LOG_FILE" 2>&1; then
  rm -f "$LOG_FILE"
  printf '[PASS] %s\n' "$LABEL"
  exit 0
else
  STATUS=$?
fi

printf '[FAIL] %s\n' "$LABEL" >&2

DIAGNOSTICS="$({
  sed $'s/\033\\[[0-9;]*[[:alpha:]]//g' "$LOG_FILE" \
    | grep -Ei '(^|[^[:alpha:]])(error|fail|failed|failure|fatal|exception|traceback|assert|panic)([^[:alpha:]]|$)|:[0-9]+(:[0-9]+)?:' \
    | tail -n 15
} || true)"

if [[ -n "$DIAGNOSTICS" ]]; then
  printf '%s\n' "$DIAGNOSTICS" >&2
else
  tail -n 15 "$LOG_FILE" >&2
fi

exit "$STATUS"
