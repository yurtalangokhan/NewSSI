# shellcheck shell=bash
# Shared file-list resolution for scripts/quality/*.sh. Source, do not execute.

# Print the base a branch without upstream forks from, so its first push covers
# every commit on it rather than only the last one. QUALITY_BASE_REF overrides
# the candidates; a candidate that already contains HEAD is not a fork point.
quality_push_base_ref() {
  local head
  local ref
  local candidates=(origin/dev dev origin/master master)

  [[ -n "${QUALITY_BASE_REF:-}" ]] && candidates=("$QUALITY_BASE_REF")
  head="$(git rev-parse HEAD)"

  for ref in "${candidates[@]}"; do
    git rev-parse --verify --quiet "$ref^{commit}" >/dev/null || continue
    [[ "$(git merge-base HEAD "$ref" 2>/dev/null)" == "$head" ]] && continue
    printf '%s\n' "$ref"
    return 0
  done
  return 1
}

# Print the files a quality mode covers: QUALITY_FILES when set, otherwise the
# staged diff, the unpushed diff, or every tracked file.
quality_changed_files() {
  local mode="$1"
  local base

  if [[ -n "${QUALITY_FILES:-}" ]]; then
    printf '%s\n' "$QUALITY_FILES"
    return
  fi

  case "$mode" in
    staged)
      git diff --cached --name-only --diff-filter=ACMR
      ;;
    push)
      if git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
        git diff --name-only --diff-filter=ACMR '@{upstream}...HEAD'
      elif base="$(quality_push_base_ref)"; then
        git diff --name-only --diff-filter=ACMR "$base...HEAD"
      else
        git diff --name-only --diff-filter=ACMR HEAD~1...HEAD 2>/dev/null \
          || git diff --name-only --diff-filter=ACMR HEAD
      fi
      ;;
    all)
      git ls-files
      ;;
    *)
      echo "Unknown quality mode: $mode" >&2
      return 2
      ;;
  esac
}
