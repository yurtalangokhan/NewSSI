#!/usr/bin/env bash
set -euo pipefail

# Idempotent Keycloak bootstrap for server-hosted Keycloak.
KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://10.101.90.13:8085}"
KEYCLOAK_ADMIN_REALM="${KEYCLOAK_ADMIN_REALM:-master}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin123}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-agenticai}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-agenticai-web}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"
KEYCLOAK_REDIRECT_URI="${KEYCLOAK_REDIRECT_URI:-*}"
KEYCLOAK_WEB_ORIGIN="${KEYCLOAK_WEB_ORIGIN:-*}"
KEYCLOAK_REDIRECT_URIS="${KEYCLOAK_REDIRECT_URIS:-$KEYCLOAK_REDIRECT_URI}"
KEYCLOAK_WEB_ORIGINS="${KEYCLOAK_WEB_ORIGINS:-$KEYCLOAK_WEB_ORIGIN}"
KEYCLOAK_POST_LOGOUT_REDIRECT_URIS="${KEYCLOAK_POST_LOGOUT_REDIRECT_URIS:-+}"
KEYCLOAK_TEST_USER="${KEYCLOAK_TEST_USER:-devuser}"
KEYCLOAK_TEST_EMAIL="${KEYCLOAK_TEST_EMAIL:-devuser@local.dev}"
KEYCLOAK_TEST_PASSWORD="${KEYCLOAK_TEST_PASSWORD:-DevPass123!}"

# Default app-admin account (used by UI for admin panel visibility)
KEYCLOAK_DEFAULT_ADMIN_USER="${KEYCLOAK_DEFAULT_ADMIN_USER:-agentic-admin}"
KEYCLOAK_DEFAULT_ADMIN_EMAIL="${KEYCLOAK_DEFAULT_ADMIN_EMAIL:-admin@agenticai.local}"
KEYCLOAK_DEFAULT_ADMIN_PASSWORD="${KEYCLOAK_DEFAULT_ADMIN_PASSWORD:-AdminPass123!}"
KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME="${KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME:-Agentic}"
KEYCLOAK_DEFAULT_ADMIN_LAST_NAME="${KEYCLOAK_DEFAULT_ADMIN_LAST_NAME:-Admin}"
KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE="${KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE:-admin}"

if [[ -z "$KEYCLOAK_CLIENT_SECRET" ]]; then
  KEYCLOAK_PUBLIC_CLIENT=true
else
  KEYCLOAK_PUBLIC_CLIENT=false
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "[error] curl command not found"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[error] jq command not found"
  echo "        Install jq to run Keycloak bootstrap over REST API"
  exit 1
fi

BASE="${KEYCLOAK_BASE_URL%/}"

echo "[info] checking keycloak availability: $BASE"
if ! curl -fsS "$BASE/realms/$KEYCLOAK_ADMIN_REALM/.well-known/openid-configuration" >/dev/null; then
  echo "[error] cannot reach keycloak at $BASE"
  exit 1
fi

echo "[info] obtaining admin token"
ADMIN_TOKEN="$({
  curl -fsS -X POST "$BASE/realms/$KEYCLOAK_ADMIN_REALM/protocol/openid-connect/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode 'client_id=admin-cli' \
    --data-urlencode "username=$KEYCLOAK_ADMIN" \
    --data-urlencode "password=$KEYCLOAK_ADMIN_PASSWORD"
} | jq -r '.access_token // empty')"

if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "[error] failed to get admin token"
  echo "        verify KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD / KEYCLOAK_BASE_URL"
  exit 1
fi

auth_header() {
  printf 'Authorization: Bearer %s' "$ADMIN_TOKEN"
}

http_code() {
  local method="$1"
  local url="$2"
  local data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url" -H "$(auth_header)" -H 'Content-Type: application/json' -d "$data"
  else
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url" -H "$(auth_header)"
  fi
}

realm_exists_code="$(http_code GET "$BASE/admin/realms/$KEYCLOAK_REALM")"
if [[ "$realm_exists_code" == "404" ]]; then
  echo "[info] creating realm: $KEYCLOAK_REALM"
  create_realm_code="$(http_code POST "$BASE/admin/realms" "{\"realm\":\"$KEYCLOAK_REALM\",\"enabled\":true}")"
  if [[ "$create_realm_code" != "201" && "$create_realm_code" != "204" ]]; then
    echo "[error] failed to create realm: HTTP $create_realm_code"
    exit 1
  fi
elif [[ "$realm_exists_code" == "200" ]]; then
  echo "[info] realm exists: $KEYCLOAK_REALM"
else
  echo "[error] failed to query realm: HTTP $realm_exists_code"
  exit 1
fi

CLIENT_SEARCH_URL="$BASE/admin/realms/$KEYCLOAK_REALM/clients?clientId=$KEYCLOAK_CLIENT_ID"
CLIENT_UUID="$({
  curl -fsS "$CLIENT_SEARCH_URL" -H "$(auth_header)"
} | jq -r '.[0].id // empty')"

if [[ -z "$CLIENT_UUID" ]]; then
  echo "[info] creating client: $KEYCLOAK_CLIENT_ID"
  create_client_payload="$(jq -n \
    --arg clientId "$KEYCLOAK_CLIENT_ID" \
    --arg redirectUrisCsv "$KEYCLOAK_REDIRECT_URIS" \
    --arg webOriginsCsv "$KEYCLOAK_WEB_ORIGINS" \
    --arg postLogoutRedirectUris "$KEYCLOAK_POST_LOGOUT_REDIRECT_URIS" \
    --argjson publicClient "$KEYCLOAK_PUBLIC_CLIENT" \
    '{
      clientId: $clientId,
      enabled: true,
      protocol: "openid-connect",
      publicClient: $publicClient,
      standardFlowEnabled: true,
      directAccessGrantsEnabled: true,
      redirectUris: ($redirectUrisCsv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))),
      webOrigins: ($webOriginsCsv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))),
      attributes: {
        "post.logout.redirect.uris": $postLogoutRedirectUris
      }
    }')"

  create_client_code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/clients" "$create_client_payload")"
  if [[ "$create_client_code" != "201" && "$create_client_code" != "204" ]]; then
    echo "[error] failed to create client: HTTP $create_client_code"
    exit 1
  fi

  CLIENT_UUID="$({
    curl -fsS "$CLIENT_SEARCH_URL" -H "$(auth_header)"
  } | jq -r '.[0].id // empty')"
else
  echo "[info] client exists: $KEYCLOAK_CLIENT_ID"
fi

if [[ -z "$CLIENT_UUID" ]]; then
  echo "[error] unable to resolve client UUID for $KEYCLOAK_CLIENT_ID"
  exit 1
fi

echo "[info] syncing client settings for: $KEYCLOAK_CLIENT_ID"
update_client_payload="$(jq -n \
  --arg clientId "$KEYCLOAK_CLIENT_ID" \
  --arg redirectUrisCsv "$KEYCLOAK_REDIRECT_URIS" \
  --arg webOriginsCsv "$KEYCLOAK_WEB_ORIGINS" \
  --arg postLogoutRedirectUris "$KEYCLOAK_POST_LOGOUT_REDIRECT_URIS" \
  --argjson publicClient "$KEYCLOAK_PUBLIC_CLIENT" \
  '{
    clientId: $clientId,
    enabled: true,
    protocol: "openid-connect",
    publicClient: $publicClient,
    standardFlowEnabled: true,
    directAccessGrantsEnabled: true,
    redirectUris: ($redirectUrisCsv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))),
    webOrigins: ($webOriginsCsv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))),
    attributes: {
      "post.logout.redirect.uris": $postLogoutRedirectUris
    }
  }')"
update_client_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$CLIENT_UUID" "$update_client_payload")"
if [[ "$update_client_code" != "200" && "$update_client_code" != "204" ]]; then
  echo "[error] failed to sync client settings: HTTP $update_client_code"
  exit 1
fi

if [[ -n "$KEYCLOAK_CLIENT_SECRET" ]]; then
  echo "[info] setting custom client secret"
  update_secret_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$CLIENT_UUID/client-secret" "{\"value\":\"$KEYCLOAK_CLIENT_SECRET\"}")"
  if [[ "$update_secret_code" != "200" && "$update_secret_code" != "204" ]]; then
    echo "[error] failed to set client secret: HTTP $update_secret_code"
    exit 1
  fi
fi

USER_SEARCH_URL="$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_TEST_USER&exact=true"
USER_UUID="$({
  curl -fsS "$USER_SEARCH_URL" -H "$(auth_header)"
} | jq -r '.[0].id // empty')"

if [[ -z "$USER_UUID" ]]; then
  echo "[info] creating test user: $KEYCLOAK_TEST_USER"
  create_user_payload="$(jq -n \
    --arg username "$KEYCLOAK_TEST_USER" \
    --arg email "$KEYCLOAK_TEST_EMAIL" \
    '{
      username: $username,
      email: $email,
      enabled: true,
      emailVerified: true
    }')"

  create_user_code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users" "$create_user_payload")"
  if [[ "$create_user_code" != "201" && "$create_user_code" != "204" ]]; then
    echo "[error] failed to create user: HTTP $create_user_code"
    exit 1
  fi

  USER_UUID="$({
    curl -fsS "$USER_SEARCH_URL" -H "$(auth_header)"
  } | jq -r '.[0].id // empty')"
else
  echo "[info] user exists: $KEYCLOAK_TEST_USER"
fi

if [[ -z "$USER_UUID" ]]; then
  echo "[error] unable to resolve user UUID for $KEYCLOAK_TEST_USER"
  exit 1
fi

echo "[info] setting password for $KEYCLOAK_TEST_USER"
set_password_payload="$(jq -n --arg password "$KEYCLOAK_TEST_PASSWORD" '{type:"password", temporary:false, value:$password}')"
set_password_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$USER_UUID/reset-password" "$set_password_payload")"
if [[ "$set_password_code" != "204" ]]; then
  echo "[error] failed to set user password: HTTP $set_password_code"
  exit 1
fi

ADMIN_SEARCH_URL="$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_DEFAULT_ADMIN_USER&exact=true"
DEFAULT_ADMIN_UUID="$({
  curl -fsS "$ADMIN_SEARCH_URL" -H "$(auth_header)"
} | jq -r '.[0].id // empty')"

if [[ -z "$DEFAULT_ADMIN_UUID" ]]; then
  echo "[info] creating default admin user: $KEYCLOAK_DEFAULT_ADMIN_USER"
  create_admin_payload="$(jq -n \
    --arg username "$KEYCLOAK_DEFAULT_ADMIN_USER" \
    --arg email "$KEYCLOAK_DEFAULT_ADMIN_EMAIL" \
    --arg firstName "$KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME" \
    --arg lastName "$KEYCLOAK_DEFAULT_ADMIN_LAST_NAME" \
    '{
      username: $username,
      email: $email,
      firstName: $firstName,
      lastName: $lastName,
      enabled: true,
      emailVerified: true,
      attributes: {
        agentic_role: ["admin"],
        invited: ["false"],
        password_configured: ["true"]
      }
    }')"

  create_admin_code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users" "$create_admin_payload")"
  if [[ "$create_admin_code" != "201" && "$create_admin_code" != "204" ]]; then
    echo "[error] failed to create default admin user: HTTP $create_admin_code"
    exit 1
  fi

  DEFAULT_ADMIN_UUID="$({
    curl -fsS "$ADMIN_SEARCH_URL" -H "$(auth_header)"
  } | jq -r '.[0].id // empty')"
else
  echo "[info] default admin user exists: $KEYCLOAK_DEFAULT_ADMIN_USER"
fi

if [[ -z "$DEFAULT_ADMIN_UUID" ]]; then
  echo "[error] unable to resolve user UUID for default admin $KEYCLOAK_DEFAULT_ADMIN_USER"
  exit 1
fi

echo "[info] syncing default admin profile and attributes"
admin_user_json="$({
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users/$DEFAULT_ADMIN_UUID" -H "$(auth_header)"
})"

sync_admin_payload="$(echo "$admin_user_json" | jq \
  --arg username "$KEYCLOAK_DEFAULT_ADMIN_USER" \
  --arg email "$KEYCLOAK_DEFAULT_ADMIN_EMAIL" \
  --arg firstName "$KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME" \
  --arg lastName "$KEYCLOAK_DEFAULT_ADMIN_LAST_NAME" \
  '.username = $username
   | .email = $email
   | .firstName = $firstName
   | .lastName = $lastName
   | .enabled = true
   | .emailVerified = true
   | .attributes = (.attributes // {})
   | .attributes.agentic_role = ["admin"]
   | .attributes.invited = ["false"]
   | .attributes.password_configured = ["true"]')"

sync_admin_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$DEFAULT_ADMIN_UUID" "$sync_admin_payload")"
if [[ "$sync_admin_code" != "200" && "$sync_admin_code" != "204" ]]; then
  echo "[error] failed to sync default admin attributes: HTTP $sync_admin_code"
  exit 1
fi

echo "[info] setting password for default admin user"
set_admin_password_payload="$(jq -n --arg password "$KEYCLOAK_DEFAULT_ADMIN_PASSWORD" '{type:"password", temporary:false, value:$password}')"
set_admin_password_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$DEFAULT_ADMIN_UUID/reset-password" "$set_admin_password_payload")"
if [[ "$set_admin_password_code" != "204" ]]; then
  echo "[error] failed to set default admin password: HTTP $set_admin_password_code"
  exit 1
fi

echo "[info] ensuring realm role exists: $KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE"
role_get_code="$(http_code GET "$BASE/admin/realms/$KEYCLOAK_REALM/roles/$KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE")"
if [[ "$role_get_code" == "404" ]]; then
  create_role_code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/roles" "$(jq -n --arg name "$KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE" '{name:$name}')")"
  if [[ "$create_role_code" != "201" && "$create_role_code" != "204" && "$create_role_code" != "409" ]]; then
    echo "[error] failed to create realm role $KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE: HTTP $create_role_code"
    exit 1
  fi
elif [[ "$role_get_code" != "200" ]]; then
  echo "[error] failed to query realm role $KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE: HTTP $role_get_code"
  exit 1
fi

role_representation="$({
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/roles/$KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE" -H "$(auth_header)"
})"
if [[ -z "$role_representation" || "$role_representation" == "null" ]]; then
  echo "[error] could not fetch realm role representation for $KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE"
  exit 1
fi

echo "[info] assigning realm role '$KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE' to $KEYCLOAK_DEFAULT_ADMIN_USER"
assign_role_code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users/$DEFAULT_ADMIN_UUID/role-mappings/realm" "[$role_representation]")"
if [[ "$assign_role_code" != "204" && "$assign_role_code" != "200" && "$assign_role_code" != "409" ]]; then
  echo "[error] failed to assign realm role to default admin: HTTP $assign_role_code"
  exit 1
fi

echo "[ok] Keycloak bootstrap complete"
echo "[ok] server=$BASE realm=$KEYCLOAK_REALM client=$KEYCLOAK_CLIENT_ID user=$KEYCLOAK_TEST_USER"
echo "[ok] default_admin_user=$KEYCLOAK_DEFAULT_ADMIN_USER default_admin_email=$KEYCLOAK_DEFAULT_ADMIN_EMAIL"
