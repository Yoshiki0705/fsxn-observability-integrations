#!/bin/bash
# Honeycomb — Post-deployment E2E verification
# Sends a test event via Events API and confirms acceptance (HTTP 200).
#
# Usage:
#   export HONEYCOMB_API_KEY="<your-api-key>"  # hcaik_ prefix
#   export HONEYCOMB_DATASET="fsxn-audit"
#   bash integrations/honeycomb/scripts/verify.sh

set -euo pipefail

HONEYCOMB_API_KEY="${HONEYCOMB_API_KEY:-}"
HONEYCOMB_DATASET="${HONEYCOMB_DATASET:-fsxn-audit}"
HONEYCOMB_ENDPOINT="${HONEYCOMB_ENDPOINT:-https://api.honeycomb.io}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Honeycomb — E2E Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${HONEYCOMB_API_KEY}" ]; then
  echo "❌ ERROR: HONEYCOMB_API_KEY must be set."
  echo ""
  echo "  export HONEYCOMB_API_KEY='hcaik_xxxx'"
  echo "  export HONEYCOMB_DATASET='fsxn-audit'"
  exit 1
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

PAYLOAD=$(cat <<EOF
[{
  "time": "${TIMESTAMP}",
  "data": {
    "event_type": "4663",
    "user": "CORP\\\\verify-test",
    "path": "/share/test/verify-ok.txt",
    "result": "Audit Success",
    "svm": "VerifySVM",
    "client_ip": "198.51.100.1",
    "operation": "ReadData",
    "source": "fsxn-verify"
  }
}]
EOF
)

echo "  Endpoint: ${HONEYCOMB_ENDPOINT}/1/batch/${HONEYCOMB_DATASET}"
echo "  Dataset: ${HONEYCOMB_DATASET}"
echo "  Sending test event..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${HONEYCOMB_ENDPOINT}/1/batch/${HONEYCOMB_DATASET}" \
  -H "Content-Type: application/json" \
  -H "X-Honeycomb-Team: ${HONEYCOMB_API_KEY}" \
  -d "${PAYLOAD}")

echo ""
if [ "${HTTP_CODE}" = "200" ]; then
  echo "  ✅ PASS — Test event accepted (HTTP ${HTTP_CODE})"
  echo ""
  echo "  Verify in Honeycomb:"
  echo "    Query → Dataset: ${HONEYCOMB_DATASET} → WHERE user = \"CORP\\verify-test\""
else
  echo "  ❌ FAIL — HTTP ${HTTP_CODE}"
  echo ""
  echo "  Troubleshooting:"
  echo "    401: Check HONEYCOMB_API_KEY (must start with hcaik_)"
  echo "    404: Dataset '${HONEYCOMB_DATASET}' may not exist"
  exit 1
fi
