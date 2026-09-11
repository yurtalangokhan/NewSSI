#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SERVICE=""
WORK_DIR=""

if (($# > 0)) && [[ "$1" == --service=* ]]; then
  SERVICE="${1#--service=}"
  shift
fi

case "$SERVICE" in
  root) WORK_DIR="$ROOT" ;;
  agent-service | rag-service | user-service | tools-service | web)
    WORK_DIR="$ROOT/apps/$SERVICE"
    ;;
  "")
    echo "Missing required argument: --service=<service>" >&2
    exit 2
    ;;
  *)
    echo "Unknown service: $SERVICE" >&2
    exit 2
    ;;
esac

if (($# < 2)) || [[ "$1" != "--" ]]; then
  echo "Usage: $0 --service=<service> -- <affected-area test command>" >&2
  exit 2
fi
shift

exec "$ROOT/scripts/validation/quiet-run.sh" "spec:$SERVICE" -- \
  bash -c 'cd "$1"; shift; exec "$@"' bash "$WORK_DIR" "$@"
