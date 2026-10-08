#!/usr/bin/env bash

set -euo pipefail

APISIX_BASE_URL="${APISIX_BASE_URL:-http://localhost:8000}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() {
  echo -e "${GREEN}PASS${NC} - $1"
}

fail() {
  echo -e "${RED}FAIL${NC} - $1"
  exit 1
}

status_code() {
  curl \
    --silent \
    --show-error \
    --output /dev/null \
    --write-out "%{http_code}" \
    "$@"
}

echo -e "${YELLOW}Apache APISIX gateway tests${NC}"
echo "Base URL: $APISIX_BASE_URL"
echo


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

CODE="$(status_code "$APISIX_BASE_URL/user-service/health")"

if [[ "$CODE" == "200" ]]; then
  pass "user-service public health"
else
  fail "user-service public health returned HTTP $CODE"
fi


CODE="$(status_code "$APISIX_BASE_URL/agent-service/health")"

if [[ "$CODE" == "200" ]]; then
  pass "agent-service public health"
else
  fail "agent-service public health returned HTTP $CODE"
fi


CODE="$(status_code "$APISIX_BASE_URL/rag-service/health")"

if [[ "$CODE" == "200" ]]; then
  pass "rag-service public health"
else
  fail "rag-service public health returned HTTP $CODE"
fi


CODE="$(status_code "$APISIX_BASE_URL/tools-service/health")"

if [[ "$CODE" == "200" ]]; then
  pass "tools-service public health"
else
  fail "tools-service public health returned HTTP $CODE"
fi


# ---------------------------------------------------------------------------
# Protected routes without token
# ---------------------------------------------------------------------------

CODE="$(
  status_code \
    "$APISIX_BASE_URL/user-service/api/v1/auth/me"
)"

if [[ "$CODE" == "401" ]]; then
  pass "user-service protected route rejects missing bearer token"
else
  fail "protected user route expected 401 but returned HTTP $CODE"
fi


CODE="$(
  status_code \
    "$APISIX_BASE_URL/rag-service/api/v1/collections"
)"

if [[ "$CODE" == "401" ]]; then
  pass "rag-service protected route rejects missing bearer token"
else
  fail "protected RAG route expected 401 but returned HTTP $CODE"
fi


# ---------------------------------------------------------------------------
# Invalid token
# ---------------------------------------------------------------------------

CODE="$(
  status_code \
    -H "Authorization: Bearer invalid-token" \
    "$APISIX_BASE_URL/user-service/api/v1/auth/me"
)"

if [[ "$CODE" == "401" ]]; then
  pass "invalid bearer token rejected"
else
  fail "invalid bearer token expected 401 but returned HTTP $CODE"
fi


# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------

HEADERS="$(
  curl \
    --silent \
    --show-error \
    --head \
    "$APISIX_BASE_URL/user-service/health"
)"

if echo "$HEADERS" | grep -qi '^X-Request-Id:'; then
  pass "X-Request-Id returned by APISIX"
else
  fail "X-Request-Id response header missing"
fi


echo
echo -e "${GREEN}Apache APISIX basic gateway tests completed successfully.${NC}"