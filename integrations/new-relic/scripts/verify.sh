#!/bin/bash
# New Relic — Post-deployment E2E verification
# Sends a test log via Log API and confirms acceptance (HTTP 202).
#
# Usage:
#   export NEW_RELIC_LICENSE_KEY="<your-license-key>"
#   export NEW_RELIC_REGION="US"  # or EU
#   bash integrations/new-relic/scripts/verify.sh

set -euo pipefail

NEW_RELIC_LICENSE_KEY="${NEW_RELIC_LICENSE_KEY:-}"
NEW_RELIC_REGION="${NEW_RELIC_REGION:-US}"

if [ "${NEW_RELIC_REGION}" = "EU" ]; then
  LOG_ENDPOINT="https://log-api.eu.newrelic.com/log/v1"
else
  LOG_ENDPOINT="https://log-api.newrelic.com/log/v1"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " New Relic — E2E Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${NEW_RELIC_LICENSE_KEY}" ]; then
  echo "❌ ERROR: NEW_RELIC_LICENSE_KEY must be set."
  echo ""
  echo "  export NEW_RELIC_LICENSE_KEY='<license-key>'"
  echo "  export NEW_RELIC_REGION='US'  # or EU"
  exit 1
fi

TIMESTAMP=$(date +%s)

PAYLOAD=$(cat <<EOF
[{
  "common": {"attributes": {"logtype": "fsxn-audit", "instrumentation.provider": "fsxn"}},
  "logs": [{
    "timestamp": ${TIMESTAMP},
    "message": "E2E verification test log",
    "attributes": {
      "event_type": "4663",
      "user": "CORP\\\\verify-test",
      "path": "/share/test/verify-ok.txt",
      "result": "Audit Success",
      "svm": "VerifySVM",
      "client_ip": "198.51.100.1",
      "operation": "ReadData"
    }
  }]
}]
EOF
)

echo "  Endpoint: ${LOG_ENDPOINT}"
echo "  Region: ${NEW_RELIC_REGION}"
echo "  Sending test log..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${LOG_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "Api-Key: ${NEW_RELIC_LICENSE_KEY}" \
  -d "${PAYLOAD}")

echo ""
if [ "${HTTP_CODE}" = "202" ]; then
  echo "  ✅ PASS — Test log accepted (HTTP ${HTTP_CODE})"
  echo ""
  echo "  Verify in New Relic:"
  echo "    Logs → WHERE instrumentation.provider = 'fsxn' AND user = 'CORP\\verify-test'"
else
  echo "  ❌ FAIL — HTTP ${HTTP_CODE}"
  echo ""
  echo "  Troubleshooting:"
  echo "    403: Check NEW_RELIC_LICENSE_KEY"
  echo "    404: Check NEW_RELIC_REGION (US vs EU)"
  exit 1
fi
