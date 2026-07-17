#!/bin/bash
# Dynatrace — Post-deployment E2E verification
# Sends a test log via Log Ingest API and confirms acceptance (HTTP 204).
#
# Usage:
#   export DT_ENV_URL="https://<env-id>.live.dynatrace.com"
#   export DT_API_TOKEN="<your-api-token>"  # Scope: logs.ingest
#   bash integrations/dynatrace/scripts/verify.sh

set -euo pipefail

DT_ENV_URL="${DT_ENV_URL:-}"
DT_API_TOKEN="${DT_API_TOKEN:-}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Dynatrace — E2E Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${DT_ENV_URL}" ] || [ -z "${DT_API_TOKEN}" ]; then
  echo "❌ ERROR: DT_ENV_URL and DT_API_TOKEN must be set."
  echo ""
  echo "  export DT_ENV_URL='https://<env-id>.live.dynatrace.com'"
  echo "  export DT_API_TOKEN='<token>'  # Scope: logs.ingest"
  exit 1
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%S.000000000Z)

PAYLOAD=$(cat <<EOF
[{
  "content": "{\"event_type\":\"4663\",\"user\":\"CORP\\\\verify-test\",\"path\":\"/share/test/verify-ok.txt\",\"result\":\"Audit Success\",\"svm\":\"VerifySVM\",\"client_ip\":\"198.51.100.1\",\"operation\":\"ReadData\"}",
  "log.source": "fsxn",
  "severity": "info",
  "timestamp": "${TIMESTAMP}",
  "dt.entity.custom_device": "fsxn-verify"
}]
EOF
)

echo "  Endpoint: ${DT_ENV_URL}/api/v2/logs/ingest"
echo "  Sending test log..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${DT_ENV_URL}/api/v2/logs/ingest" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "Authorization: Api-Token ${DT_API_TOKEN}" \
  -d "${PAYLOAD}")

echo ""
if [ "${HTTP_CODE}" = "204" ]; then
  echo "  ✅ PASS — Test log accepted (HTTP ${HTTP_CODE})"
  echo ""
  echo "  Verify in Dynatrace:"
  echo "    Observe → Logs → DQL: fetch logs | filter matchesValue(log.source, \"fsxn\") | filter matchesValue(content, \"verify-test\")"
elif [ "${HTTP_CODE}" = "200" ]; then
  echo "  ✅ PASS — Test log accepted (HTTP ${HTTP_CODE})"
else
  echo "  ❌ FAIL — HTTP ${HTTP_CODE}"
  echo ""
  echo "  Troubleshooting:"
  echo "    401: Check DT_API_TOKEN"
  echo "    403: Token may lack 'logs.ingest' scope"
  echo "    413: Payload too large (should not happen with single log)"
  exit 1
fi
