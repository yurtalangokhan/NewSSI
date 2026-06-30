#!/usr/bin/env bash
set -euo pipefail

# Idempotent Keycloak bootstrap for agenticai realm.
# Creates:
#   - agenticai-web  (public client — frontend login)
#   - user-service   (confidential, service account)
#   - agent-service  (confidential, service account)
#   - rag-service    (confidential, service account)
#   - tools-service  (confidential, service account)
#   - Initial realm roles: system-admin, enterprise-admin, enduser
#   - Protocol mappers on agenticai-web for permissions claim

KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://10.101.90.13:8085}"
KEYCLOAK_ADMIN_REALM="${KEYCLOAK_ADMIN_REALM:-master}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin123}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-agenticai}"

# Frontend client (public)
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-agenticai-web}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"
KEYCLOAK_REDIRECT_URI="${KEYCLOAK_REDIRECT_URI:-*}"
KEYCLOAK_WEB_ORIGIN="${KEYCLOAK_WEB_ORIGIN:-*}"
KEYCLOAK_REDIRECT_URIS="${KEYCLOAK_REDIRECT_URIS:-$KEYCLOAK_REDIRECT_URI}"
KEYCLOAK_WEB_ORIGINS="${KEYCLOAK_WEB_ORIGINS:-$KEYCLOAK_WEB_ORIGIN}"
KEYCLOAK_POST_LOGOUT_REDIRECT_URIS="${KEYCLOAK_POST_LOGOUT_REDIRECT_URIS:-+}"

# Backend service clients (confidential, service-account enabled)
BACKEND_CLIENTS=("user-service" "agent-service" "rag-service" "tools-service")

# Env file directory (used to write generated secrets)
ENV_DIR="${ENV_DIR:-/home/nuhyurduseven/codes/agenticai/apps}"

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
  echo "[info] creating client: $clientId"
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

# ---------------------------------------------------------------------------
# 2. Frontend client: agenticai-web (public)
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
update_code="$(http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$FE_UUID" "$(jq -n \
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
[[ "$update_code" == "200" || "$update_code" == "204" ]] || echo "[warn] frontend client update returned HTTP $update_code"

if [[ -n "$KEYCLOAK_CLIENT_SECRET" ]]; then
  echo "[info] setting custom client secret for $KEYCLOAK_CLIENT_ID"
  http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$FE_UUID/client-secret" "{\"value\":\"$KEYCLOAK_CLIENT_SECRET\"}" > /dev/null
fi

# ---------------------------------------------------------------------------
# 3. Backend service clients (confidential, service-account enabled)
# ---------------------------------------------------------------------------
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
    # Update existing client to ensure serviceAccountsEnabled etc.
    update_payload="$(jq -n --arg clientId "$CLIENT" '{clientId: $clientId, enabled: true, protocol: "openid-connect", publicClient: false, standardFlowEnabled: false, directAccessGrantsEnabled: false, serviceAccountsEnabled: true}')"
    http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$UUID" "$update_payload" > /dev/null
  fi
  # Generate and set secret
  SECRET="$(generate_secret)"
  http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/clients/$UUID/client-secret" "{\"value\":\"$SECRET\"}" > /dev/null
  SECRETS["$CLIENT"]="$SECRET"
  echo "[info]   secret set for $CLIENT"
done

# ---------------------------------------------------------------------------
# 4. Realm roles (system-admin, enterprise-admin, enduser)
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

# 5. Protocol mappers — NOT created.
#    Fine-grained permissions no longer appear in the JWT.
#    Only Keycloak's default resource_access with coarse roles is used.

# ---------------------------------------------------------------------------
# 6. Test user
# ---------------------------------------------------------------------------
USER_UUID="$(
  curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_TEST_USER&exact=true" -H "$(auth_header)" \
  | jq -r '.[0].id // empty'
)"
if [[ -z "$USER_UUID" ]]; then
  echo "[info] creating test user: $KEYCLOAK_TEST_USER"
  http_code POST "$BASE/admin/realms/$KEYCLOAK_REALM/users" "$(jq -n \
    --arg username "$KEYCLOAK_TEST_USER" --arg email "$KEYCLOAK_TEST_EMAIL" \
    '{username: $username, email: $email, enabled: true, emailVerified: true}')" > /dev/null
  USER_UUID="$(
    curl -fsS "$BASE/admin/realms/$KEYCLOAK_REALM/users?username=$KEYCLOAK_TEST_USER&exact=true" -H "$(auth_header)" \
    | jq -r '.[0].id // empty'
  )"
fi
echo "[info] setting password for $KEYCLOAK_TEST_USER"
http_code PUT "$BASE/admin/realms/$KEYCLOAK_REALM/users/$USER_UUID/reset-password" \
  "$(jq -n --arg password "$KEYCLOAK_TEST_PASSWORD" '{type:"password", temporary:false, value:$password}')" > /dev/null

# ---------------------------------------------------------------------------
# 7. Default admin user
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
# 8. Print summary + secrets for .env files
# ---------------------------------------------------------------------------
echo ""
echo "[ok] ===== Keycloak bootstrap complete ====="
echo "[ok] realm:            $KEYCLOAK_REALM"
echo "[ok] frontend client:  $KEYCLOAK_CLIENT_ID (public)"
echo ""

for CLIENT in "${BACKEND_CLIENTS[@]}"; do
  echo "[ok] backend client:   $CLIENT (confidential, service-account)"
done

echo ""
echo "[ok] Realm roles: ${REALM_ROLES[*]}"
echo "[ok] Protocol mappers: permissions-{user-service,agent-service,rag-service,tools-service} -> permissions claim"
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

write_env "user-service"   "user-service"   "${SECRETS[user-service]}"
write_env "agent-service"  "agent-service"  "${SECRETS[agent-service]}"
write_env "rag-service"    "rag-service"    "${SECRETS[rag-service]}"
write_env "tools-service"  "tools-service"  "${SECRETS[tools-service]}"

echo ""
echo "[ok] Bootstrap finished successfully"
