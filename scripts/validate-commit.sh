#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

exec "$ROOT/scripts/validation/quiet-run.sh" "commit" -- \
  bash "$ROOT/scripts/quality/check.sh" staged
