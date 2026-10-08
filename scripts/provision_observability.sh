#!/bin/sh
# Provision the Elasticsearch side of the observability platform.
#
# Runs once, as a Compose bootstrap service, after Elasticsearch is healthy.
# It is idempotent: every request is a PUT of the same definition, so a restart
# or a re-run converges on the same state instead of duplicating anything.
#
# What it installs:
#   - an ILM policy: logs roll over and are deleted after LOG_RETENTION_DAYS
#   - an index template for logs-*: the field contract's identifiers are
#     keyword-typed so filters and aggregations work, and the ILM policy is
#     attached
#   - an index template for otel-traces: the trace identifiers are keyword-typed
#     so a trace can be joined to its log records by one value
#
# Without this template, Elasticsearch maps the first document it sees
# dynamically: a request_id that arrives as text is mapped as text, and every
# later filter or aggregation on it behaves inconsistently. The template makes
# the field contract hold on the platform side, not just in the records.

set -eu

ES_URL="${ELASTICSEARCH_URL:?ELASTICSEARCH_URL is required}"
RETENTION_DAYS="${LOG_RETENTION_DAYS:?LOG_RETENTION_DAYS is required}"

# --- ILM policy: delete logs after the retention window ----------------------
curl -fsS -X PUT "$ES_URL/_ilm/policy/observability-logs" \
  -H 'Content-Type: application/json' -d @- <<EOF
{
  "policy": {
    "phases": {
      "hot": { "actions": {} },
      "delete": { "min_age": "${RETENTION_DAYS}d", "actions": { "delete": {} } }
    }
  }
}
EOF
echo " (ilm policy)"

# --- Index template: the log field contract, platform-side -------------------
curl -fsS -X PUT "$ES_URL/_index_template/observability-logs" \
  -H 'Content-Type: application/json' -d @- <<EOF
{
  "index_patterns": ["logs-*"],
  "priority": 200,
  "template": {
    "settings": {
      "index.lifecycle.name": "observability-logs",
      "number_of_shards": 1,
      "number_of_replicas": 0
    },
    "mappings": {
      "properties": {
        "timestamp":   { "type": "date" },
        "level":       { "type": "keyword" },
        "service":     { "type": "keyword" },
        "logger":      { "type": "keyword" },
        "event":       { "type": "keyword" },
        "message":     { "type": "text" },
        "request_id":  { "type": "keyword" },
        "trace_id":    { "type": "keyword" },
        "user_id":     { "type": "keyword" },
        "module":      { "type": "keyword" },
        "function":    { "type": "keyword" },
        "line":        { "type": "integer" },
        "operation":   { "type": "keyword" },
        "dependency":  { "type": "keyword" },
        "attempt":     { "type": "integer" },
        "max_attempts": { "type": "integer" },
        "elapsed_ms":  { "type": "float" },
        "status":      { "type": "keyword" },
        "error": {
          "properties": {
            "exception_type":    { "type": "keyword" },
            "exception_message": { "type": "text" },
            "retryable":         { "type": "boolean" },
            "hint":              { "type": "text" }
          }
        }
      }
    }
  }
}
EOF
echo " (logs template)"

# --- Index template: traces, joined to logs by trace_id ----------------------
curl -fsS -X PUT "$ES_URL/_index_template/otel-traces" \
  -H 'Content-Type: application/json' -d @- <<EOF
{
  "index_patterns": ["otel-traces"],
  "priority": 200,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    },
    "mappings": {
      "properties": {
        "trace_id": { "type": "keyword" },
        "span_id":  { "type": "keyword" },
        "parent_span_id": { "type": "keyword" },
        "service.name":   { "type": "keyword" },
        "platform.request_id": { "type": "keyword" },
        "http.request.method": { "type": "keyword" },
        "url.path":  { "type": "keyword" },
        "duration":  { "type": "long" }
      }
    }
  }
}
EOF
echo " (traces template)"

echo "observability provisioning complete"
