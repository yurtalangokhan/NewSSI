#!/usr/bin/env bash

set -euo pipefail

# Migrate data from legacy shared DB into isolated service DBs.
#
# Usage:
#   scripts/migrate_shared_postgres_to_service_dbs.sh --plan
#   scripts/migrate_shared_postgres_to_service_dbs.sh --execute

MODE="plan"
if [[ "${1:-}" == "--execute" ]]; then
  MODE="execute"
elif [[ "${1:-}" == "--plan" || -z "${1:-}" ]]; then
  MODE="plan"
else
  echo "Unknown argument: ${1:-}" >&2
  echo "Use --plan or --execute" >&2
  exit 1
fi

PGHOST="${PGHOST:-10.101.90.13}"
PGPORT="${PGPORT:-8124}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-your-super-secret-and-long-postgres-password}"

SOURCE_DB="${SOURCE_DB:-postgres}"
AGENT_DB="${AGENT_DB:-agent_service}"
RAG_DB="${RAG_DB:-rag_service}"

# Service-scoped tables we want to migrate.
agent_tables=(
  assistant
  thread
  checkpoints
  checkpoint_writes
  checkpoint_blobs
  store
  langchain_pg_collection
  langchain_pg_embedding
  persona
  mcp_provider
  mcp_tool
  agent_definitions
  agent_tools
  datasource_airbyte_mapping
  sync_schedules
)

rag_tables=(
  langchain_pg_collection
  langchain_pg_embedding
)

export PGPASSWORD

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd psql

psql_base=(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -v ON_ERROR_STOP=1 -P pager=off)

table_exists() {
  local db="$1"
  local table_name="$2"
  local exists
  exists=$("${psql_base[@]}" -d "$db" -At -c "
    SELECT EXISTS (
      SELECT 1
      FROM information_schema.tables
      WHERE table_schema='public' AND table_name='${table_name}'
    );
  ")
  [[ "$exists" == "t" ]]
}

list_columns() {
  local db="$1"
  local table_name="$2"
  "${psql_base[@]}" -d "$db" -At -c "
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name='${table_name}'
    ORDER BY ordinal_position;
  "
}

common_columns_in_source_order() {
  local source_db="$1"
  local target_db="$2"
  local table_name="$3"

  local src_file tgt_file
  src_file="$(mktemp)"
  tgt_file="$(mktemp)"

  list_columns "$source_db" "$table_name" >"$src_file"
  list_columns "$target_db" "$table_name" | sort >"$tgt_file"

  while IFS= read -r col; do
    [[ -z "$col" ]] && continue
    if grep -Fxq "$col" "$tgt_file"; then
      echo "$col"
    fi
  done <"$src_file"

  rm -f "$src_file" "$tgt_file"
}

count_rows() {
  local db="$1"
  local table_name="$2"
  "${psql_base[@]}" -d "$db" -At -c "SELECT COUNT(*) FROM public.\"${table_name}\";"
}

migrate_one_table() {
  local source_db="$1"
  local target_db="$2"
  local table_name="$3"

  if ! table_exists "$source_db" "$table_name" || ! table_exists "$target_db" "$table_name"; then
    echo " - ${table_name}: skipped (table missing in source or target)"
    return
  fi

  mapfile -t cols < <(common_columns_in_source_order "$source_db" "$target_db" "$table_name")
  if [[ "${#cols[@]}" -eq 0 ]]; then
    echo " - ${table_name}: skipped (no common columns)"
    return
  fi

  local joined_cols
  joined_cols=$(printf '"%s",' "${cols[@]}")
  joined_cols="${joined_cols%,}"

  local src_count tgt_count
  src_count="$(count_rows "$source_db" "$table_name")"
  tgt_count="$(count_rows "$target_db" "$table_name")"

  if [[ "$MODE" == "plan" ]]; then
    echo " - ${table_name}: ${src_count} -> ${tgt_count}"
    return
  fi

  "${psql_base[@]}" -d "$target_db" -c "TRUNCATE TABLE public.\"${table_name}\" RESTART IDENTITY CASCADE;" >/dev/null

  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$source_db" -v ON_ERROR_STOP=1 -c \
    "COPY (SELECT ${joined_cols} FROM public.\"${table_name}\") TO STDOUT WITH (FORMAT CSV)" \
    | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$target_db" -v ON_ERROR_STOP=1 -c \
      "COPY public.\"${table_name}\" (${joined_cols}) FROM STDIN WITH (FORMAT CSV)"

  echo " - ${table_name}: ${src_count} -> $(count_rows "$target_db" "$table_name")"
}

migrate_group() {
  local target_db="$1"
  shift
  local tables=("$@")

  echo
  echo "== ${SOURCE_DB} -> ${target_db} =="
  for t in "${tables[@]}"; do
    migrate_one_table "$SOURCE_DB" "$target_db" "$t"
  done
}

echo "Mode: ${MODE}"
echo "Postgres: ${PGHOST}:${PGPORT}"
echo "Source DB: ${SOURCE_DB}"

migrate_group "$AGENT_DB" "${agent_tables[@]}"
migrate_group "$RAG_DB" "${rag_tables[@]}"

echo

echo "Done"
