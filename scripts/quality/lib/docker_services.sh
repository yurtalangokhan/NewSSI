# shellcheck shell=bash
# Resolve which Python service images a change affects, from each image's own
# Dockerfile, so build triggers never drift from what the images copy.
# Source, do not execute.

QUALITY_DOCKER_SERVICES=(agent-service rag-service user-service tools-service)

# Files every image build depends on: compose build definitions, the Makefile
# targets that drive the build, and the shared build-context filter.
QUALITY_DOCKER_SHARED_INPUTS='^(deploy/docker/docker-compose.*\.ya?ml|configs/docker-compose.*\.ya?ml|docker-compose.*\.ya?ml|\.dockerignore|Makefile)$'

# Build definitions are read from here, so Dockerfile renames need no edits.
QUALITY_COMPOSE_FILE="${QUALITY_COMPOSE_FILE:-deploy/docker/docker-compose-dev.yml}"

# Print a service's Dockerfile, repo-relative, from its compose `build` block
# (`context` + `dockerfile`, or the short `build: <context>` form). Fails when
# the service or its Dockerfile is missing, so a drift can't skip a build.
quality_service_dockerfile() {
  local service="$1"
  local root
  local build
  local context_dir
  local relative_context
  local dockerfile

  root="$(git rev-parse --show-toplevel)"
  build="$(
    awk -v service="$service" '
      function value(line) {
        sub(/^[^:]*:[[:space:]]*/, "", line)
        sub(/[[:space:]]+#.*$/, "", line)
        gsub(/^["'\'']|["'\'']$/, "", line)
        return line
      }
      /^[^[:space:]#]/ { in_services = ($0 ~ /^services:/); current = ""; next }
      in_services && /^  [^[:space:]#][^:]*:/ {
        current = $1; sub(/:$/, "", current); in_build = 0; next
      }
      current != service { next }
      /^    build:[[:space:]]*$/ { in_build = 1; found = 1; next }
      /^    build:/ { context = value($0); found = 1; next }
      /^    [^[:space:]]/ { in_build = 0; next }
      in_build && /^      context:/ { context = value($0) }
      in_build && /^      dockerfile:/ { dockerfile = value($0) }
      END {
        if (found) printf "%s\t%s\n", (context == "" ? "." : context), (dockerfile == "" ? "Dockerfile" : dockerfile)
      }
    ' "$root/$QUALITY_COMPOSE_FILE"
  )"

  if [[ -z "$build" ]]; then
    echo "error: $service has no build definition in $QUALITY_COMPOSE_FILE" >&2
    return 1
  fi

  context_dir="$(cd "$(dirname "$root/$QUALITY_COMPOSE_FILE")/${build%%$'\t'*}" 2>/dev/null && pwd -P)" || {
    echo "error: $service build context not found (from $QUALITY_COMPOSE_FILE)" >&2
    return 1
  }
  relative_context="${context_dir#"$(cd "$root" && pwd -P)"}"
  relative_context="${relative_context#/}"
  dockerfile="${relative_context:+$relative_context/}${build#*$'\t'}"

  if [[ ! -f "$root/$dockerfile" ]]; then
    echo "error: $service Dockerfile $dockerfile (from $QUALITY_COMPOSE_FILE) does not exist" >&2
    return 1
  fi
  printf '%s\n' "$dockerfile"
}

# Print the Dockerfile and every build-context COPY/ADD source it reads.
# Copies from another build stage (`--from=`) are not build-context inputs.
quality_docker_build_inputs() {
  local dockerfile="$1"

  printf '%s\n' "$dockerfile"
  awk '
    toupper($1) == "COPY" || toupper($1) == "ADD" {
      for (i = 2; i <= NF; i++) if ($i ~ /^--from=/) next
      for (i = 2; i < NF; i++) if ($i !~ /^--/) print $i
    }
  ' "$dockerfile"
}

# Anchored ERE matching any repo path inside one of the given inputs.
quality_inputs_pattern() {
  local input
  local pattern=""

  while IFS= read -r input; do
    input="${input//./\\.}"
    if [[ "$input" == */ ]]; then
      pattern+="${pattern:+|}^$input"
    else
      pattern+="${pattern:+|}^$input(/|\$)"
    fi
  done
  printf '%s\n' "$pattern"
}

# Read a changed-file list on stdin; print the affected services, space separated.
quality_docker_services() {
  local files
  local service
  local dockerfile
  local dockerfiles=()
  local affected=()
  local index

  files="$(cat)"

  # Resolve every service first: a broken build definition fails the gate
  # even when this change would not rebuild that service.
  for service in "${QUALITY_DOCKER_SERVICES[@]}"; do
    dockerfile="$(quality_service_dockerfile "$service")" || return 1
    dockerfiles+=("$dockerfile")
  done

  if grep -Eq "$QUALITY_DOCKER_SHARED_INPUTS" <<<"$files"; then
    printf '%s\n' "${QUALITY_DOCKER_SERVICES[*]}"
    return
  fi

  for index in "${!QUALITY_DOCKER_SERVICES[@]}"; do
    if grep -Eq "$(quality_docker_build_inputs "${dockerfiles[index]}" | quality_inputs_pattern)" <<<"$files"; then
      affected+=("${QUALITY_DOCKER_SERVICES[index]}")
    fi
  done

  printf '%s\n' "${affected[*]}"
}
