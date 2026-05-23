#!/bin/bash
# New Relic E2E Verification — Quick Execution Guide
#
# This script guides you through the E2E verification steps.
# Run each section manually or execute the full script.
#
# Prerequisites:
#   - New Relic account (Free Tier: 100 GB/month)
#   - AWS CLI configured
#   - FSx ONTAP S3 Access Point with audit logs
#
# Usage:
#   export NR_LICENSE_KEY="your-40-char-license-key"
#   export NR_ACCOUNT_ID="your-account-id"
#   export NR_API_KEY="your-user-api-key"  # For NerdGraph queries
#   export S3_ACCESS_POINT_ARN="arn:aws:s3:..."
#   export S3_BUCKET_NAME="your-bucket"
#   bash integrations/new-relic/scripts/e2e-verify.sh

set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
STACK_NAME="${STACK_NAME:-fsxn-new-relic-integration}"
NR_LICENSE_KEY="${NR_LICENSE_KEY:-}"
NR_ACCOUNT_ID="${NR_ACCOUNT_ID:-}"
NR_API_KEY="${NR_API_KEY:-}"
S3_ACCESS_POINT_ARN="${S3_ACCESS_POINT_ARN:-}"
S3_BUCKET_NAME="${S3_BUCKET_NAME:-}"

echo "=== New Relic E2E Verification ==="
echo "Region: ${AWS_REGION}"
echo "Stack: ${STACK_NAME}"
echo ""

# --- Step 1: Store License Key in Secrets Manager ---
echo "--- Step 1: Secrets Manager Setup ---"
if [ -z "${NR_LICENSE_KEY}" ]; then
  echo "  NR_LICENSE_KEY not set. Skipping secret creation."
  echo "  Set it and re-run, or create manually:"
  echo "  aws secretsmanager create-secret --name new-relic/fsxn-license-key \\"
  echo "    --secret-string '{\"license_key\":\"YOUR_KEY\"}' --region ${AWS_REGION}"
else
  SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id "new-relic/fsxn-license-key" \
    --region "${AWS_REGION}" \
    --query 'ARN' --output text 2>/dev/null || echo "")

  if [ -z "${SECRET_ARN}" ]; then
    echo "  Creating secret..."
    SECRET_ARN=$(aws secretsmanager create-secret \
      --name "new-relic/fsxn-license-key" \
      --secret-string "{\"license_key\":\"${NR_LICENSE_KEY}\"}" \
      --region "${AWS_REGION}" \
      --query 'ARN' --output text)
    echo "  Secret created: ${SECRET_ARN}"
  else
    echo "  Secret exists: ${SECRET_ARN}"
  fi
  export NR_SECRET_ARN="${SECRET_ARN}"
fi

# --- Step 2: Deploy Stack ---
echo ""
echo "--- Step 2: Deploy CloudFormation Stack ---"
if [ -n "${NR_SECRET_ARN:-}" ] && [ -n "${S3_ACCESS_POINT_ARN}" ] && [ -n "${S3_BUCKET_NAME}" ]; then
  bash "$(dirname "$0")/deploy.sh" --audit-only
  echo "  Stack deployed"
else
  echo "  Missing required vars. Deploy manually:"
  echo "  export NR_SECRET_ARN=<secret-arn>"
  echo "  export S3_ACCESS_POINT_ARN=<s3-ap-arn>"
  echo "  export S3_BUCKET_NAME=<bucket>"
  echo "  bash integrations/new-relic/scripts/deploy.sh --audit-only"
fi

# --- Step 3: Invoke Lambda with test event ---
echo ""
echo "--- Step 3: Lambda Test Invocation ---"
FUNCTION_NAME="${STACK_NAME}-shipper"
TEST_EVENT="integrations/new-relic/tests/test_data/sample_s3_event.json"

if [ -f "${TEST_EVENT}" ]; then
  echo "  Invoking ${FUNCTION_NAME}..."
  aws lambda invoke \
    --function-name "${FUNCTION_NAME}" \
    --payload "file://${TEST_EVENT}" \
    --cli-binary-format raw-in-base64-out \
    --region "${AWS_REGION}" \
    /tmp/nr-response.json > /dev/null 2>&1 || true

  if [ -f /tmp/nr-response.json ]; then
    echo "  Response: $(cat /tmp/nr-response.json)"
    rm -f /tmp/nr-response.json
  fi
else
  echo "  Test event not found: ${TEST_EVENT}"
fi

# --- Step 4: Verify in New Relic via NerdGraph ---
echo ""
echo "--- Step 4: New Relic Log Verification ---"
if [ -n "${NR_API_KEY}" ] && [ -n "${NR_ACCOUNT_ID}" ]; then
  echo "  Querying NerdGraph for recent logs..."
  NRQL="SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 15 minutes ago"
  QUERY_PAYLOAD="{\"query\":\"{ actor { account(id: ${NR_ACCOUNT_ID}) { nrql(query: \\\"${NRQL}\\\") { results } } } }\"}"
  RESULT=$(curl -s -X POST "https://api.newrelic.com/graphql" \
    -H "Content-Type: application/json" \
    -H "API-Key: ${NR_API_KEY}" \
    -d "${QUERY_PAYLOAD}")
  echo "  NRQL: ${NRQL}"
  echo "  Result: ${RESULT}"
else
  echo "  NR_API_KEY or NR_ACCOUNT_ID not set. Verify manually:"
  echo "  NRQL: SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 15 minutes ago"
fi

# --- Step 5: Screenshot Reminders ---
echo ""
echo "--- Step 5: Screenshots Required ---"
echo "  Capture and save to docs/screenshots/new-relic/:"
echo "  1. logs-ui-arrival.png — Logs UI showing fsxn-ontap events"
echo "  2. nrql-query-result.png — NRQL query with results"
echo "  3. alert-condition-config.png — Alert condition setup"
echo "  4. alert-policy-overview.png — Alert policy overview"
echo ""
echo "  After capturing, run mask script:"
echo "  python3 docs/screenshots/mask_screenshots.py"

# --- Summary ---
echo ""
echo "=== Verification Summary ==="
echo "  Stack: ${STACK_NAME}"
echo "  Lambda: ${FUNCTION_NAME}"
echo "  NRQL: SELECT * FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago"
echo ""
echo "  Next: Capture screenshots, then run:"
echo "  python3 scripts/generate-results.py --vendor new-relic"
