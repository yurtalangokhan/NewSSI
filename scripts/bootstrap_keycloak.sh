#!/usr/bin/env bash
set -euo pipefail

# Keycloak bootstrap for the agenticai-v1 realm.
# Creates:
#   - web-client  (public client — frontend login)
#   - user-service-client   (confidential, service account)
#   - agent-service-client  (confidential, service account)
#   - rag-service-client    (confidential, service account)
#   - tools-service-client  (confidential, service account)
#   - Initial realm roles: system-admin, enterprise-admin, enduser
#   - Token contents of the login client (gateway audience, groups and primary_role claims, realm
#     scope mappings instead of "Full scope allowed") and the gateway authorization objects:
#     bootstrap_gateway_authorization.py, run at the end

KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://10.101.90.13:8085}"
KEYCLOAK_ADMIN_REALM="${KEYCLOAK_ADMIN_REALM:-master}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin123}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:?KEYCLOAK_REALM must be set from configs/.env}"

# Frontend client (public)
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:?KEYCLOAK_CLIENT_ID must be set from configs/.env}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"
KEYCLOAK_REDIRECT_URI="${KEYCLOAK_REDIRECT_URI:-*}"
KEYCLOAK_WEB_ORIGIN="${KEYCLOAK_WEB_ORIGIN:-*}"
KEYCLOAK_REDIRECT_URIS="${KEYCLOAK_REDIRECT_URIS:-$KEYCLOAK_REDIRECT_URI}"
KEYCLOAK_WEB_ORIGINS="${KEYCLOAK_WEB_ORIGINS:-$KEYCLOAK_WEB_ORIGIN}"
KEYCLOAK_POST_LOGOUT_REDIRECT_URIS="${KEYCLOAK_POST_LOGOUT_REDIRECT_URIS:-+}"


# Backend service clients (confidential, service-account enabled)
BACKEND_CLIENTS=(
  "${KEYCLOAK_USER_SERVICE_CLIENT_ID:?KEYCLOAK_USER_SERVICE_CLIENT_ID is required}"
  "${KEYCLOAK_AGENT_SERVICE_CLIENT_ID:?KEYCLOAK_AGENT_SERVICE_CLIENT_ID is required}"
  "${KEYCLOAK_RAG_SERVICE_CLIENT_ID:?KEYCLOAK_RAG_SERVICE_CLIENT_ID is required}"
  "${KEYCLOAK_TOOLS_SERVICE_CLIENT_ID:?KEYCLOAK_TOOLS_SERVICE_CLIENT_ID is required}"
)

# Env file directory (used to write generated secrets).
# Defaults to <repo>/apps, resolved from this script's own location so it works
# for any checkout; override with ENV_DIR when the apps tree lives elsewhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${ENV_DIR:-$(cd "$SCRIPT_DIR/../apps" 2>/dev/null && pwd || echo "$SCRIPT_DIR/../apps")}"

# Users
KEYCLOAK_TEST_USER="${KEYCLOAK_TEST_USER:-devuser}"
KEYCLOAK_TEST_EMAIL="${KEYCLOAK_TEST_EMAIL:-devuser@local.dev}"
KEYCLOAK_TEST_PASSWORD="${KEYCLOAK_TEST_PASSWORD:-DevPass123!}"

KEYCLOAK_DEFAULT_ADMIN_USER="${KEYCLOAK_DEFAULT_ADMIN_USER:-agentic-admin}"
KEYCLOAK_DEFAULT_ADMIN_EMAIL="${KEYCLOAK_DEFAULT_ADMIN_EMAIL:-admin@agenticai.local}"
KEYCLOAK_DEFAULT_ADMIN_PASSWORD="${KEYCLOAK_DEFAULT_ADMIN_PASSWORD:-AdminPass123!}"
KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME="${KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME:-Agentic}"
KEYCLOAK_DEFAULT_ADMIN_LAST_NAME="${KEYCLOAK_DEFAULT_ADMIN_LAST_NAME:-Admin}"

# Realm roles to create
REALM_ROLES=("system-admin" "enterprise-admin" "enduser")

if [[ -z "$KEYCLOAK_CLIENT_SECRET" ]]; then
  KEYCLOAK_PUBLIC_CLIENT=true
else
  KEYCLOAK_PUBLIC_CLIENT=false
fi

if ! command -v curl >/dev/null 2>&1; then echo "[error] curl not found"; exit 1; fi
if ! command -v jq >/dev/null 2>&1;   then echo "[error] jq not found";   exit 1; fi

BASE="${KEYCLOAK_BASE_URL%/}"

echo "[info] checking keycloak availability: $BASE"
curl -fsS "$BASE/realms/$KEYCLOAK_ADMIN_REALM/.well-known/openid-configuration" >/dev/null || {
  echo "[error] cannot reach keycloak at $BASE"; exit 1
}

echo "[info] obtaining admin token"
ADMIN_TOKEN="$(
  curl -fsS -X POST "$BASE/realms/$KEYCLOAK_ADMIN_REALM/protocol/openid-connect/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode 'client_id=admin-cli' \
    --data-urlencode "username=$KEYCLOAK_ADMIN" \
    --data-urlencode "password=$KEYCLOAK_ADMIN_PASSWORD" \
  | jq -r '.access_token // empty'
)"
[[ -n "$ADMIN_TOKEN" ]] || { echo "[error] failed to get admin token"; exit 1; }

auth_header() { printf 'Authorization: Bearer %s' "$ADMIN_TOKEN"; }

http_code() {
  local method="$1" url="$2" data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url" -H "$(auth_header)" -H 'Content-Type: application/json' -d "$data"
  else
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url" -H "$(auth_header)"
  fi
}

# ---------------------------------------------------------------------------
# 1. Realm
# ---------------------------------------------------------------------------
realm_code="$(http_code GET "$BASE/admin/realms/$KEYCLOAK_REALM")"
if [[ "$realm_code" == "404" ]]; then
  echo "[info] creating realm: $KEYCLOAK_REALM"
  code="$(http_code POST "$BASE/admin/realms" "{\"realm\":\"$KEYCLOAK_REALM\",\"enabled\":true}")"
  [[ "$code" == "201" || "$code" == "204" ]] || { echo "[error] failed to create realm: HTTP $code"; exit 1; }
elif [[ "$realm_code" == "200" ]]; then
  echo "[info] realm exists: $KEYCLOAK_REALM"
else
  echo "[error] failed to query realm: HTTP $realm_code"; exit 1
fi

# ---------------------------------------------------------------------------
# Helper: get-or-create client, returns UUID
# ---------------------------------------------------------------------------
ensure_client() {
  local clientId="$1"
  shift
  local uuid
  uuid="$(
    curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/clients?clientId=$clientId" -H "$(auth_header)" \
    | jq -r '.[0].id // empty'
  )"
  if [[ -n "$uuid" ]]; then
    echo "$uuid"
    return 0
  fi
  local payload="$1"
  echo "[info] creating client: $clientId" >&2
  code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/clients" "$payload")"
  [[ "$code" == "201" || "$code" == "204" ]] || { echo "[error] failed to create client $clientId: HTTP $code"; return 1; }
  uuid="$(
    curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/clients?clientId=$clientId" -H "$(auth_header)" \
    | jq -r '.[0].id // empty'
  )"
  echo "$uuid"
}

generate_secret() {
  python3 -c "import secrets; print(secrets.token_urlsafe(36)[:48])"
}

csv_json_array() {
  jq -cn --arg csv "$1" '$csv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))'
}

post_logout_json_array() {
  jq -cn --arg values "$1" '$values | split("##") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))'
}

# ---------------------------------------------------------------------------
# 2. Frontend client: web-client (public)
# ---------------------------------------------------------------------------
echo "[info] ensuring frontend client: $KEYCLOAK_CLIENT_ID"
FE_UUID="$(ensure_client "$KEYCLOAK_CLIENT_ID" "$(jq -n \
  --arg clientId "$KEYCLOAK_CLIENT_ID" \
  --arg redirectUrisCsv "$KEYCLOAK_REDIRECT_URIS" \
  --arg webOriginsCsv "$KEYCLOAK_WEB_ORIGINS" \
  --arg postLogoutRedirectUris "$KEYCLOAK_POST_LOGOUT_REDIRECT_URIS" \
  --argjson publicClient "$KEYCLOAK_PUBLIC_CLIENT" \
  '{
    clientId: $clientId, enabled: true, protocol: "openid-connect",
    publicClient: $publicClient,
    standardFlowEnabled: true, directAccessGrantsEnabled: true,
    redirectUris: ($redirectUrisCsv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))),
    webOrigins: ($webOriginsCsv | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))),
    attributes: { "post.logout.redirect.uris": $postLogoutRedirectUris }
  }')")"

echo "[info] syncing frontend client settings"
FE_CURRENT="$(
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$FE_UUID" -H "$(auth_header)"
)"
update_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$FE_UUID" "$(jq -n \
  --argjson current "$FE_CURRENT" \
  --arg clientId "$KEYCLOAK_CLIENT_ID" \
  --argjson configuredRedirectUris "$(csv_json_array "$KEYCLOAK_REDIRECT_URIS")" \
  --argjson configuredWebOrigins "$(csv_json_array "$KEYCLOAK_WEB_ORIGINS")" \
  --argjson configuredPostLogoutRedirectUris "$(post_logout_json_array "$KEYCLOAK_POST_LOGOUT_REDIRECT_URIS")" \
  --argjson publicClient "$KEYCLOAK_PUBLIC_CLIENT" \
  '$current + {
    clientId: $clientId, enabled: true, protocol: "openid-connect",
    publicClient: $publicClient,
    standardFlowEnabled: true, directAccessGrantsEnabled: true,
    redirectUris: (reduce ((($current.redirectUris // []) + $configuredRedirectUris)[]) as $uri ([]; if index($uri) then . else . + [$uri] end)),
    webOrigins: (reduce ((($current.webOrigins // []) + $configuredWebOrigins)[]) as $origin ([]; if index($origin) then . else . + [$origin] end)),
    attributes: (($current.attributes // {}) + {
      "post.logout.redirect.uris": (
        reduce (((($current.attributes // {})["post.logout.redirect.uris"] // "" | split("##") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))) + $configuredPostLogoutRedirectUris)[]) as $uri
        ([]; if index($uri) then . else . + [$uri] end) | join("##")
      )
    })
  }')")"
[[ "$update_code" == "200" || "$update_code" == "204" ]] || echo "[warn] frontend client update returned HTTP $update_code"

if [[ -n "$KEYCLOAK_CLIENT_SECRET" ]]; then
  echo "[info] setting custom client secret for $KEYCLOAK_CLIENT_ID"
  http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$FE_UUID/client-secret" "{\"value\":\"$KEYCLOAK_CLIENT_SECRET\"}" > /dev/null
fi


# ---------------------------------------------------------------------------
# 4. Backend service clients (confidential, service-account enabled)
# ---------------------------------------------------------------------------
# A client update replaces the whole representation: send the current one plus the
# settings the bootstrap enforces. A PUT without authorizationServicesEnabled makes
# Keycloak disable authorization services and delete the client's resources and policies.
BACKEND_CLIENT_UPDATE='$current + {
  clientId: $clientId, enabled: true, protocol: "openid-connect", publicClient: false,
  standardFlowEnabled: false, directAccessGrantsEnabled: false, serviceAccountsEnabled: true
}'
declare -A SECRETS
for CLIENT in "${BACKEND_CLIENTS[@]}"; do
  echo "[info] ensuring backend client: $CLIENT"
  UUID="$(
    curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/clients?clientId=$CLIENT" -H "$(auth_header)" \
    | jq -r '.[0].id // empty'
  )"
  if [[ -z "$UUID" ]]; then
    echo "[info]   creating client: $CLIENT"
    payload="$(jq -n --arg clientId "$CLIENT" '{clientId: $clientId, enabled: true, protocol: "openid-connect", publicClient: false, standardFlowEnabled: false, directAccessGrantsEnabled: false, serviceAccountsEnabled: true, attributes: {}}')"
    code="$(http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/clients" "$payload")"
    [[ "$code" == "201" || "$code" == "204" ]] || { echo "[error] failed to create client $CLIENT: HTTP $code"; exit 1; }
    UUID="$(
      curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/clients?clientId=$CLIENT" -H "$(auth_header)" \
      | jq -r '.[0].id // empty'
    )"
  else
    echo "[info]   updating existing client: $CLIENT"
    current="$(curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$UUID" -H "$(auth_header)")"
    update_payload="$(jq -n --argjson current "$current" --arg clientId "$CLIENT" "$BACKEND_CLIENT_UPDATE")"
    http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$UUID" "$update_payload" > /dev/null
  fi
  # Generate and set secret
  SECRET="$(generate_secret)"
  http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$UUID/client-secret" "{\"value\":\"$SECRET\"}" > /dev/null
  SECRETS["$CLIENT"]="$SECRET"
  echo "[info]   secret set for $CLIENT"
done

# ---------------------------------------------------------------------------
# 5. Realm roles (system-admin, enterprise-admin, enduser)
# ---------------------------------------------------------------------------
for ROLE in "${REALM_ROLES[@]}"; do
  code="$(http_code GET "$BASE/admin/realms/$KEYCLOAK_REALM/roles/$ROLE")"
  if [[ "$code" == "404" ]]; then
    echo "[info] creating realm role: $ROLE"
    http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/roles" "$(jq -n --arg name "$ROLE" '{name: $name, description: $name}')" > /dev/null
  else
    echo "[info] realm role exists: $ROLE"
  fi
done

# 6 Protocol mappers and token scope: bootstrap_gateway_authorization.py (step 9).
#    Fine-grained permissions never appear in the JWT; the token carries only the platform
#    realm roles above (realm scope mappings, no "Full scope allowed").

# ---------------------------------------------------------------------------
# 7. Test user
# ---------------------------------------------------------------------------
# The realm's user profile requires a first and a last name: a user without them cannot
# log in ("Account is not fully set up") until the profile is completed.
TEST_USER_UPDATE='$current + {
  firstName: (if ($current.firstName // "") == "" then "Test" else $current.firstName end),
  lastName: (if ($current.lastName // "") == "" then "User" else $current.lastName end)
}'
USER_UUID="$(
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_TEST_USER&exact=true" -H "$(auth_header)" \
  | jq -r '.[0].id // empty'
)"
if [[ -z "$USER_UUID" ]]; then
  echo "[info] creating test user: $KEYCLOAK_TEST_USER"
  new_user="$(jq -n --arg username "$KEYCLOAK_TEST_USER" --arg email "$KEYCLOAK_TEST_EMAIL" \
    '{username: $username, email: $email, enabled: true, emailVerified: true}')"
  http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users" \
    "$(jq -n --argjson current "$new_user" "$TEST_USER_UPDATE")" > /dev/null
  USER_UUID="$(
    curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_TEST_USER&exact=true" -H "$(auth_header)" \
    | jq -r '.[0].id // empty'
  )"
else
  current="$(curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users/$USER_UUID" -H "$(auth_header)")"
  if [[ "$(jq -r '(.firstName // "") == "" or (.lastName // "") == ""' <<<"$current")" == "true" ]]; then
    echo "[info] completing the profile of $KEYCLOAK_TEST_USER (first and last name)"
    http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$USER_UUID" \
      "$(jq -n --argjson current "$current" "$TEST_USER_UPDATE")" > /dev/null
  fi
fi
echo "[info] setting password for $KEYCLOAK_TEST_USER"
http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$USER_UUID/reset-password" \
  "$(jq -n --arg password "$KEYCLOAK_TEST_PASSWORD" '{type:"password", temporary:false, value:$password}')" > /dev/null

# ---------------------------------------------------------------------------
# 8. Default admin user
# ---------------------------------------------------------------------------
ADMIN_UUID="$(
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_DEFAULT_ADMIN_USER&exact=true" -H "$(auth_header)" \
  | jq -r '.[0].id // empty'
)"
if [[ -z "$ADMIN_UUID" ]]; then
  echo "[info] creating admin user: $KEYCLOAK_DEFAULT_ADMIN_USER"
  http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users" "$(jq -n \
    --arg username "$KEYCLOAK_DEFAULT_ADMIN_USER" \
    --arg email "$KEYCLOAK_DEFAULT_ADMIN_EMAIL" \
    --arg firstName "$KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME" \
    --arg lastName "$KEYCLOAK_DEFAULT_ADMIN_LAST_NAME" \
    '{
      username: $username, email: $email, firstName: $firstName, lastName: $lastName,
      enabled: true, emailVerified: true,
      attributes: { agentic_role: ["admin"], invited: ["false"], password_configured: ["true"] }
    }')" > /dev/null
  ADMIN_UUID="$(
    curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_DEFAULT_ADMIN_USER&exact=true" -H "$(auth_header)" \
    | jq -r '.[0].id // empty'
  )"
fi
echo "[info] setting password for $KEYCLOAK_DEFAULT_ADMIN_USER"
http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$ADMIN_UUID/reset-password" \
  "$(jq -n --arg password "$KEYCLOAK_DEFAULT_ADMIN_PASSWORD" '{type:"password", temporary:false, value:$password}')" > /dev/null

# Assign system-admin realm role to default admin
echo "[info] assigning system-admin realm role to default admin"
ROLE_REPR="$(
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/roles/system-admin" -H "$(auth_header)"
)"
http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users/$ADMIN_UUID/role-mappings/realm" "[$ROLE_REPR]" > /dev/null

# ---------------------------------------------------------------------------
# 9. Print summary + secrets for .env files
# ---------------------------------------------------------------------------
echo "[info] reconciling gateway authorization resources and policies"
KEYCLOAK_BASE_URL="$KEYCLOAK_BASE_URL" \
KEYCLOAK_REALM="$KEYCLOAK_REALM" \
KEYCLOAK_CLIENT_ID="$KEYCLOAK_CLIENT_ID" \
KEYCLOAK_BOOTSTRAP_ADMIN_TOKEN="$ADMIN_TOKEN" \
KEYCLOAK_ADMIN_REALM="$KEYCLOAK_ADMIN_REALM" \
KEYCLOAK_ADMIN="$KEYCLOAK_ADMIN" \
KEYCLOAK_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
  python3 "$(dirname "${BASH_SOURCE[0]}")/bootstrap_gateway_authorization.py"

echo ""
echo "[ok] ===== Keycloak bootstrap complete ====="
echo "[ok] realm:            $KEYCLOAK_REALM"
echo "[ok] frontend client:  $KEYCLOAK_CLIENT_ID (public)"
echo ""

for CLIENT in "${BACKEND_CLIENTS[@]}"; do
  echo "[ok] backend client:   $CLIENT (confidential, service-account)"
done

echo ""
echo "[ok] Realm roles: ${REALM_ROLES[*]} (the only roles mapped into $KEYCLOAK_CLIENT_ID tokens)"
echo ""
echo "============================================"
echo "  BACKEND SERVICE CLIENT SECRETS"
echo "  (add these to per-service .env files)"
echo "============================================"
for CLIENT in "${BACKEND_CLIENTS[@]}"; do
  echo ""
  echo "# $CLIENT"
  echo "KEYCLOAK_CLIENT_ID=$CLIENT"
  echo "KEYCLOAK_CLIENT_SECRET=${SECRETS[$CLIENT]}"
  echo "KEYCLOAK_AUDIENCE=$CLIENT"
done

echo ""
echo "============================================"
echo "  Generated secrets written to .env files"
echo "============================================"

# Attempt to write secrets to .env files
write_env() {
  local service_dir="$1" client_id="$2" secret="$3"
  local env_file="$ENV_DIR/$service_dir/.env"
  if [[ -f "$env_file" ]]; then
    # Remove any existing KEYCLOAK_* lines to avoid duplicates
    sed -i "/^KEYCLOAK_CLIENT_ID=/d" "$env_file" 2>/dev/null || true
    sed -i "/^#KEYCLOAK_CLIENT_ID=/d" "$env_file" 2>/dev/null || true
    sed -i "/^KEYCLOAK_CLIENT_SECRET=/d" "$env_file" 2>/dev/null || true
    sed -i "/^KEYCLOAK_AUDIENCE=/d" "$env_file" 2>/dev/null || true
    sed -i "/^# === BACKEND SERVICE CLIENT (bootstrap generated) ===$/d" "$env_file" 2>/dev/null || true
    # Add new entries
    {
      echo ""
      echo "# === BACKEND SERVICE CLIENT (bootstrap generated) ==="
      echo "KEYCLOAK_CLIENT_ID=$client_id"
      echo "KEYCLOAK_CLIENT_SECRET=$secret"
      echo "KEYCLOAK_AUDIENCE=$client_id"
    } >> "$env_file"
    echo "[ok]   wrote secret to $env_file"
  else
    echo "[warn]  $env_file not found — skip auto-write"
  fi
}

write_env "user-service"   "$KEYCLOAK_USER_SERVICE_CLIENT_ID"   "${SECRETS[$KEYCLOAK_USER_SERVICE_CLIENT_ID]}"
write_env "agent-service"  "$KEYCLOAK_AGENT_SERVICE_CLIENT_ID"  "${SECRETS[$KEYCLOAK_AGENT_SERVICE_CLIENT_ID]}"
write_env "rag-service"    "$KEYCLOAK_RAG_SERVICE_CLIENT_ID"    "${SECRETS[$KEYCLOAK_RAG_SERVICE_CLIENT_ID]}"
write_env "tools-service"  "$KEYCLOAK_TOOLS_SERVICE_CLIENT_ID"  "${SECRETS[$KEYCLOAK_TOOLS_SERVICE_CLIENT_ID]}"

echo ""
echo "[ok] Bootstrap finished successfully"


# =============================================================================
# Apache APISIX authorization bootstrap
# =============================================================================

echo
echo "[info] configuring Apache APISIX authorization scopes and audience"

SCRIPT_DIR="$(
  cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1
  pwd
)"

bash "${SCRIPT_DIR}/bootstrap_apisix_security.sh"

echo "[info] Apache APISIX authorization bootstrap completed"