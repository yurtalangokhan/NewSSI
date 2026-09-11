#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SERVICE=""

if (($# > 0)); then
  if [[ "$1" != --service=* ]] || (($# != 1)); then
    echo "Usage: $0 [--service=<service>]" >&2
    exit 2
  fi
  SERVICE="${1#--service=}"
fi

case "$SERVICE" in
  agent-service | rag-service | user-service | tools-service | web)
    exec "$ROOT/scripts/validation/quiet-run.sh" "push:$SERVICE" -- \
      make -C "$ROOT/apps/$SERVICE" validate
    ;;
  "")
    exec "$ROOT/scripts/validation/quiet-run.sh" "push" -- \
      bash "$ROOT/scripts/quality/check.sh" push
    ;;
  *)
    echo "Unknown service: $SERVICE" >&2
    exit 2
    ;;
esac
