#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
git -C "$ROOT" config core.hooksPath scripts/git-hooks

echo "Git hooks installed: core.hooksPath=scripts/git-hooks"
