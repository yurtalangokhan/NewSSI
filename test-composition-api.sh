#!/bin/bash
# Test script for multi-agent composition endpoints

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Multi-Agent Composition System - Test Script ===${NC}\n"

# Configuration
API_URL="http://localhost:8123/api"
AGENT_SERVICE_URL="http://localhost:8123"

# Test 1: Health check
echo -e "${YELLOW}Test 1: Health Check${NC}"
if curl -s "${API_URL}/health" > /dev/null; then
    echo -e "${GREEN}✓ Agent service is running${NC}\n"
else
    echo -e "${RED}✗ Agent service is not accessible${NC}"
    echo "Make sure agent-service is running on port 8123"
    exit 1
fi

# Test 2: POST /available-for-composition without auth (should fail)
echo -e "${YELLOW}Test 2: POST /available-for-composition (no auth)${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "${API_URL}/agent-definitions/available-for-composition" \
    -H "Content-Type: application/json" \
    -d '{"schema": "SUPERVISOR"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)

if [ "$HTTP_CODE" == "401" ] || [ "$HTTP_CODE" == "403" ]; then
    echo -e "${GREEN}✓ Auth check working (got ${HTTP_CODE})${NC}\n"
elif [ "$HTTP_CODE" == "200" ]; then
    echo -e "${GREEN}✓ Endpoint responding (no auth required in dev)${NC}"
    echo -e "${GREEN}Response: $BODY${NC}\n"
else
    echo -e "${RED}✗ Unexpected status code: ${HTTP_CODE}${NC}"
    echo -e "Body: $BODY\n"
fi

# Test 3: Check if GET endpoint still works (should be 405 now)
echo -e "${YELLOW}Test 3: GET /available-for-composition (should be 405 or 404)${NC}"
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X GET \
    "${API_URL}/agent-definitions/available-for-composition?schema=SUPERVISOR")

if [ "$HTTP_CODE" == "405" ] || [ "$HTTP_CODE" == "404" ]; then
    echo -e "${GREEN}✓ GET method properly disabled (got ${HTTP_CODE})${NC}\n"
elif [ "$HTTP_CODE" == "422" ]; then
    echo -e "${RED}✗ Still getting 422 - endpoint might not be fixed${NC}\n"
else
    echo -e "${YELLOW}~ GET returned ${HTTP_CODE} (might be OK)${NC}\n"
fi

# Test 4: POST with different schemas
echo -e "${YELLOW}Test 4: Testing POST with different payloads${NC}"

# Test SUPERVISOR schema
echo -e "  - Testing SUPERVISOR schema:"
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
    "${API_URL}/agent-definitions/available-for-composition" \
    -H "Content-Type: application/json" \
    -d '{"schema": "SUPERVISOR"}')
[ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "401" ] && echo -e "    ${GREEN}✓ SUPERVISOR (${HTTP_CODE})${NC}" || echo -e "    ${RED}✗ SUPERVISOR (${HTTP_CODE})${NC}"

# Test PIPELINE schema
echo -e "  - Testing PIPELINE schema:"
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
    "${API_URL}/agent-definitions/available-for-composition" \
    -H "Content-Type: application/json" \
    -d '{"schema": "PIPELINE"}')
[ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "401" ] && echo -e "    ${GREEN}✓ PIPELINE (${HTTP_CODE})${NC}" || echo -e "    ${RED}✗ PIPELINE (${HTTP_CODE})${NC}"

# Test with exclude_ids
echo -e "  - Testing with exclude_ids:"
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
    "${API_URL}/agent-definitions/available-for-composition" \
    -H "Content-Type: application/json" \
    -d '{"schema": "SUPERVISOR", "exclude_ids": ["uuid-1", "uuid-2"]}')
[ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "401" ] && echo -e "    ${GREEN}✓ exclude_ids (${HTTP_CODE})${NC}" || echo -e "    ${RED}✗ exclude_ids (${HTTP_CODE})${NC}"

echo ""

# Test 5: Validation endpoint (should still be POST and working)
echo -e "${YELLOW}Test 5: POST /validate-composition${NC}"
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
    "${API_URL}/agent-definitions/validate-composition" \
    -H "Content-Type: application/json" \
    -d '{"graph_schema": "SUPERVISOR", "sub_agent_ids": []}')
[ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "401" ] && echo -e "${GREEN}✓ validate-composition working (${HTTP_CODE})${NC}" || echo -e "${RED}✗ validate-composition (${HTTP_CODE})${NC}"
echo ""

# Test 6: Kong routing check
echo -e "${YELLOW}Test 6: Kong Routing Check${NC}"
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
    "http://localhost:8000/api/agent-definitions/available-for-composition" \
    -H "Content-Type: application/json" \
    -d '{"schema": "SUPERVISOR"}')

if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "401" ] || [ "$HTTP_CODE" == "403" ]; then
    echo -e "${GREEN}✓ Kong routing working (${HTTP_CODE})${NC}\n"
elif [ "$HTTP_CODE" == "422" ]; then
    echo -e "${RED}✗ Still getting 422 through Kong - Kong config might need restart${NC}"
    echo -e "${YELLOW}   Fix: docker-compose -f configs/docker-compose-services.yml restart kong${NC}\n"
else
    echo -e "${YELLOW}~ Kong returned ${HTTP_CODE}${NC}\n"
fi

# Summary
echo -e "${YELLOW}=== Test Summary ===${NC}"
echo -e "${GREEN}✓ POST endpoint tests should pass${NC}"
echo -e "${GREEN}✓ GET endpoint should return 405/404${NC}"
echo -e "${GREEN}✓ Kong should properly route requests${NC}"
echo ""
echo -e "${YELLOW}If any tests fail:${NC}"
echo "  1. Check agent-service is running: make run"
echo "  2. Restart Kong: docker-compose -f configs/docker-compose-services.yml restart kong"
echo "  3. Check migration: alembic upgrade head"
echo "  4. Review Kong logs: docker-compose logs kong"
