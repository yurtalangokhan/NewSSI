#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# Creates:
#   - user-api client scope
#   - agent-api client scope
#   - rag-api client scope
#   - tools-api client scope
#
# Assigns them as default scopes to the NewSSI Web client.
#
# Adds the APISIX gateway client as an audience to Web access tokens:
#
#   aud = apisix-gateway
#
# The script is idempotent.
# =============================================================================


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

KEYCLOAK_BASE_URL="${
  KEYCLOAK_BASE_URL:-${
    KEYCLOAK_INTERNAL_URL:-${
      KEYCLOAK_URL:-http://keycloak:8080
    }
  }
}"

KEYCLOAK_REALM="${KEYCLOAK_REALM:-agenticai}"

KEYCLOAK_ADMIN_USERNAME="${
  KEYCLOAK_ADMIN_USERNAME:-${
    KEYCLOAK_ADMIN:-admin
  }
}"

KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-}"

WEB_CLIENT_ID="${
  KEYCLOAK_CLIENT_ID:-agenticai-web
}"

APISIX_OIDC_CLIENT_ID="${
  APISIX_OIDC_CLIENT_ID:-apisix-gateway
}"


# -----------------------------------------------------------------------------
# Required commands
# -----------------------------------------------------------------------------

for command in curl jq; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "[error] required command not found: $command"
    exit 1
  fi
done


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

if [[ -z "$KEYCLOAK_ADMIN_PASSWORD" ]]; then
  echo "[error] KEYCLOAK_ADMIN_PASSWORD must not be empty"
  exit 1
fi


# Remove trailing slash.
KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL%/}"


echo "[info] Keycloak URL    : $KEYCLOAK_BASE_URL"
echo "[info] Realm           : $KEYCLOAK_REALM"
echo "[info] Web client      : $WEB_CLIENT_ID"
echo "[info] APISIX audience : $APISIX_OIDC_CLIENT_ID"


# -----------------------------------------------------------------------------
# Obtain Keycloak admin token
# -----------------------------------------------------------------------------

echo "[info] obtaining Keycloak admin token"

ADMIN_TOKEN="$(
  curl \
    --fail \
    --silent \
    --show-error \
    --request POST \
    "${KEYCLOAK_BASE_URL}/realms/master/protocol/openid-connect/token" \
    --header "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "grant_type=password" \
    --data-urlencode "client_id=admin-cli" \
    --data-urlencode "username=${KEYCLOAK_ADMIN_USERNAME}" \
    --data-urlencode "password=${KEYCLOAK_ADMIN_PASSWORD}" \
  | jq -r '.access_token'
)"

if [[ -z "$ADMIN_TOKEN" || "$ADMIN_TOKEN" == "null" ]]; then
  echo "[error] failed to obtain Keycloak admin token"
  exit 1
fi


AUTH_HEADER="Authorization: Bearer ${ADMIN_TOKEN}"
CONTENT_HEADER="Content-Type: application/json"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

get_client_uuid() {
  local client_id="$1"

  curl \
    --fail \
    --silent \
    --show-error \
    "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients?clientId=${client_id}" \
    --header "$AUTH_HEADER" \
  | jq -r '.[0].id // empty'
}


get_client_scope_id() {
  local scope_name="$1"

  curl \
    --fail \
    --silent \
    --show-error \
    "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/client-scopes" \
    --header "$AUTH_HEADER" \
  | jq -r \
      --arg scope_name "$scope_name" \
      '.[] | select(.name == $scope_name) | .id' \
  | head -n 1
}


create_client_scope_if_missing() {
  local scope_name="$1"
  local description="$2"
  local order="$3"

  local existing_id

  existing_id="$(get_client_scope_id "$scope_name")"

  if [[ -n "$existing_id" ]]; then
    echo "[info] client scope already exists: $scope_name"
    return
  fi

  echo "[info] creating client scope: $scope_name"

  local payload

  payload="$(
    jq -n \
      --arg name "$scope_name" \
      --arg description "$description" \
      --arg order "$order" \
      '{
        name: $name,
        description: $description,
        protocol: "openid-connect",
        attributes: {
          "include.in.token.scope": "true",
          "display.on.consent.screen": "false",
          "gui.order": $order
        }
      }'
  )"

  local http_code

  http_code="$(
    curl \
      --silent \
      --show-error \
      --output /tmp/keycloak-client-scope-response.json \
      --write-out "%{http_code}" \
      --request POST \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/client-scopes" \
      --header "$AUTH_HEADER" \
      --header "$CONTENT_HEADER" \
      --data "$payload"
  )"

  if [[ "$http_code" != "201" && "$http_code" != "204" ]]; then
    echo "[error] failed to create client scope: $scope_name"
    echo "[error] HTTP status: $http_code"

    if [[ -f /tmp/keycloak-client-scope-response.json ]]; then
      cat /tmp/keycloak-client-scope-response.json
      echo
    fi

    exit 1
  fi

  echo "[info] created client scope: $scope_name"
}


assign_default_client_scope() {
  local client_uuid="$1"
  local scope_name="$2"

  local scope_id

  scope_id="$(get_client_scope_id "$scope_name")"

  if [[ -z "$scope_id" ]]; then
    echo "[error] client scope not found: $scope_name"
    exit 1
  fi

  local already_assigned

  already_assigned="$(
    curl \
      --fail \
      --silent \
      --show-error \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/default-client-scopes" \
      --header "$AUTH_HEADER" \
    | jq -r \
        --arg scope_name "$scope_name" \
        'any(.name == $scope_name)'
  )"

  if [[ "$already_assigned" == "true" ]]; then
    echo "[info] default client scope already assigned: $scope_name"
    return
  fi

  echo "[info] assigning default client scope: $scope_name"

  local http_code

  http_code="$(
    curl \
      --silent \
      --show-error \
      --output /tmp/keycloak-scope-assignment-response.txt \
      --write-out "%{http_code}" \
      --request PUT \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/default-client-scopes/${scope_id}" \
      --header "$AUTH_HEADER"
  )"

  if [[ "$http_code" != "204" ]]; then
    echo "[error] failed to assign default client scope: $scope_name"
    echo "[error] HTTP status: $http_code"

    if [[ -f /tmp/keycloak-scope-assignment-response.txt ]]; then
      cat /tmp/keycloak-scope-assignment-response.txt
      echo
    fi

    exit 1
  fi

  echo "[info] assigned default client scope: $scope_name"
}


ensure_apisix_audience_mapper() {
  local client_uuid="$1"

  local mapper_name="apisix-gateway-audience"

  local mapper_id

  mapper_id="$(
    curl \
      --fail \
      --silent \
      --show-error \
      "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/protocol-mappers/models" \
      --header "$AUTH_HEADER" \
    | jq -r \
        --arg mapper_name "$mapper_name" \
        '.[] | select(.name == $mapper_name) | .id' \
    | head -n 1
  )"

  local payload

  payload="$(
    jq -n \
      --arg name "$mapper_name" \
      --arg audience "$APISIX_OIDC_CLIENT_ID" \
      '{
        name: $name,
        protocol: "openid-connect",
        protocolMapper: "oidc-audience-mapper",
        consentRequired: false,
        config: {
          "included.client.audience": $audience,
          "id.token.claim": "false",
          "access.token.claim": "true",
          "introspection.token.claim": "true",
          "lightweight.claim": "false"
        }
      }'
  )"

  local http_code

  if [[ -z "$mapper_id" ]]; then

    echo "[info] creating APISIX audience mapper"

    http_code="$(
      curl \
        --silent \
        --show-error \
        --output /tmp/keycloak-audience-mapper-response.json \
        --write-out "%{http_code}" \
        --request POST \
        "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/protocol-mappers/models" \
        --header "$AUTH_HEADER" \
        --header "$CONTENT_HEADER" \
        --data "$payload"
    )"

    if [[ "$http_code" != "201" && "$http_code" != "204" ]]; then
      echo "[error] failed to create APISIX audience mapper"
      echo "[error] HTTP status: $http_code"

      if [[ -f /tmp/keycloak-audience-mapper-response.json ]]; then
        cat /tmp/keycloak-audience-mapper-response.json
        echo
      fi

      exit 1
    fi

  else

    echo "[info] updating APISIX audience mapper"

    http_code="$(
      curl \
        --silent \
        --show-error \
        --output /tmp/keycloak-audience-mapper-response.json \
        --write-out "%{http_code}" \
        --request PUT \
        "${KEYCLOAK_BASE_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/protocol-mappers/models/${mapper_id}" \
        --header "$AUTH_HEADER" \
        --header "$CONTENT_HEADER" \
        --data "$payload"
    )"

    if [[ "$http_code" != "204" ]]; then
      echo "[error] failed to update APISIX audience mapper"
      echo "[error] HTTP status: $http_code"

      if [[ -f /tmp/keycloak-audience-mapper-response.json ]]; then
        cat /tmp/keycloak-audience-mapper-response.json
        echo
      fi

      exit 1
    fi

  fi

  echo "[info] APISIX audience mapper configured"
}


# -----------------------------------------------------------------------------
# Validate clients
# -----------------------------------------------------------------------------

echo "[info] resolving Web client"

WEB_CLIENT_UUID="$(get_client_uuid "$WEB_CLIENT_ID")"

if [[ -z "$WEB_CLIENT_UUID" ]]; then
  echo "[error] Web client not found: $WEB_CLIENT_ID"
  exit 1
fi


echo "[info] resolving APISIX client"

APISIX_CLIENT_UUID="$(
  get_client_uuid "$APISIX_OIDC_CLIENT_ID"
)"

if [[ -z "$APISIX_CLIENT_UUID" ]]; then
  echo "[error] APISIX client not found: $APISIX_OIDC_CLIENT_ID"
  echo "[error] run the normal Keycloak bootstrap first"
  exit 1
fi


# -----------------------------------------------------------------------------
# Create NewSSI API scopes
# -----------------------------------------------------------------------------

create_client_scope_if_missing \
  "newssi-user-api" \
  "Allows access to the NewSSI User Service external API." \
  "100"

create_client_scope_if_missing \
  "newssi-agent-api" \
  "Allows access to the NewSSI Agent Service external API." \
  "110"

create_client_scope_if_missing \
  "newssi-rag-api" \
  "Allows access to the NewSSI RAG Service external API." \
  "120"

create_client_scope_if_missing \
  "newssi-tools-api" \
  "Allows access to the NewSSI Tools Service external API." \
  "130"


# -----------------------------------------------------------------------------
# Assign scopes to Web client
# -----------------------------------------------------------------------------

assign_default_client_scope \
  "$WEB_CLIENT_UUID" \
  "newssi-user-api"

assign_default_client_scope \
  "$WEB_CLIENT_UUID" \
  "newssi-agent-api"

assign_default_client_scope \
  "$WEB_CLIENT_UUID" \
  "newssi-rag-api"

assign_default_client_scope \
  "$WEB_CLIENT_UUID" \
  "newssi-tools-api"


# -----------------------------------------------------------------------------
# Audience
# -----------------------------------------------------------------------------

ensure_apisix_audience_mapper "$WEB_CLIENT_UUID"


# -----------------------------------------------------------------------------
# Finish
# -----------------------------------------------------------------------------

echo
echo "[info] APISIX / Keycloak authorization bootstrap completed"
echo
echo "[info] Expected access-token scopes:"
echo "       newssi-user-api"
echo "       newssi-agent-api"
echo "       newssi-rag-api"
echo "       newssi-tools-api"
echo
echo "[info] Expected audience:"
echo "       $APISIX_OIDC_CLIENT_ID"