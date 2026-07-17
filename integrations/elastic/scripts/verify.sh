#!/bin/bash
# Elastic — Post-deployment E2E verification
# Sends a test log via Bulk API and confirms acceptance (HTTP 200).
#
# Usage:
#   export ELASTIC_URL="https://<cluster-id>.es.<region>.aws.cloud.es.io:9243"
#   export ELASTIC_API_KEY="<your-api-key>"
#   bash integrations/elastic/scripts/verify.sh

set -euo pipefail

ELASTIC_URL="${ELASTIC_URL:-}"
ELASTIC_API_KEY="${ELASTIC_API_KEY:-}"
ELASTIC_INDEX="${ELASTIC_INDEX:-fsxn-audit}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Elastic — E2E Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${ELASTIC_URL}" ] || [ -z "${ELASTIC_API_KEY}" ]; then
  echo "❌ ERROR: ELASTIC_URL and ELASTIC_API_KEY must be set."
  echo ""
  echo "  export ELASTIC_URL='https://<cluster>.es.<region>.aws.cloud.es.io:9243'"
  echo "  export ELASTIC_API_KEY='<base64-encoded-api-key>'"
  exit 1
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)

PAYLOAD=$(printf '{"index":{"_index":"%s"}}\n{"@timestamp":"%s","event.dataset":"fsxn","event.action":"ReadData","user.name":"CORP\\\\verify-test","file.path":"/share/test/verify-ok.txt","source.ip":"198.51.100.1","event.outcome":"success","observer.name":"VerifySVM","message":"E2E verification test log"}\n' "${ELASTIC_INDEX}" "${TIMESTAMP}")

echo "  Endpoint: ${ELASTIC_URL}/_bulk"
echo "  Index: ${ELASTIC_INDEX}"
echo "  Sending test log..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${ELASTIC_URL}/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  -H "Authorization: ApiKey ${ELASTIC_API_KEY}" \
  -d "${PAYLOAD}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo ""
if [ "${HTTP_CODE}" = "200" ]; then
  ERRORS=$(echo "${BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('errors',True))" 2>/dev/null || echo "true")
  if [ "${ERRORS}" = "False" ]; then
    echo "  ✅ PASS — Test log indexed (HTTP ${HTTP_CODE}, errors=false)"
    echo ""
    echo "  Verify in Kibana:"
    echo "    Discover → index: ${ELASTIC_INDEX} → user.name: \"CORP\\verify-test\""
  else
    echo "  ⚠️  PARTIAL — HTTP 200 but bulk response has errors"
    echo "  Response: ${BODY}"
    exit 1
  fi
else
  echo "  ❌ FAIL — HTTP ${HTTP_CODE}"
  echo ""
  echo "  Troubleshooting:"
  echo "    401: Check ELASTIC_API_KEY"
  echo "    403: API key may lack index write permission"
  echo "    404: Check ELASTIC_URL"
  exit 1
fi
