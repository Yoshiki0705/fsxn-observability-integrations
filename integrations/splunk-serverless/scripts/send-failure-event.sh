#!/usr/bin/env bash
# send-failure-event.sh — Send Failure (unauthorized access) audit log events via Lambda
#
# Usage:
#   ./send-failure-event.sh [--region REGION] [--function-name NAME]
#
# Environment Variables:
#   AWS_REGION          - AWS region (default: ap-northeast-1)
#   LAMBDA_FUNCTION     - Lambda function name (default: fsxn-splunk-log-shipper)
#
# This script invokes the Lambda log shipper with a test S3 event payload
# that references audit logs containing Result=Failure events, simulating
# unauthorized access attempts for the demo scenario.

set -euo pipefail

# --- Configuration ---
REGION="${AWS_REGION:-ap-northeast-1}"
FUNCTION_NAME="${LAMBDA_FUNCTION:-fsxn-splunk-log-shipper}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RESPONSE_FILE="/tmp/send-failure-event-response.json"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --region)
      REGION="$2"
      shift 2
      ;;
    --function-name)
      FUNCTION_NAME="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--region REGION] [--function-name NAME]"
      echo ""
      echo "Send Failure audit log events via Lambda for unauthorized access demo."
      echo ""
      echo "Options:"
      echo "  --region          AWS region (default: ap-northeast-1)"
      echo "  --function-name   Lambda function name (default: fsxn-splunk-log-shipper)"
      echo "  -h, --help        Show this help message"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1"
      exit 1
      ;;
  esac
done

# --- Preflight checks ---
echo "=== Demo Scenario 1: Unauthorized Access Detection ==="
echo ""
echo "Configuration:"
echo "  Region:    ${REGION}"
echo "  Function:  ${FUNCTION_NAME}"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
  echo "ERROR: AWS CLI is not installed or not in PATH"
  exit 1
fi

# Check test data exists
TEST_EVENT="${PROJECT_DIR}/tests/test_data/sample_s3_event.json"
if [[ ! -f "${TEST_EVENT}" ]]; then
  echo "ERROR: Test event file not found: ${TEST_EVENT}"
  echo "  Expected: integrations/splunk-serverless/tests/test_data/sample_s3_event.json"
  exit 1
fi

# --- Step 1: Invoke Lambda with test event ---
echo "Step 1: Invoking Lambda function with Failure event payload..."
echo "  Payload: ${TEST_EVENT}"
echo ""

aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --payload "file://${TEST_EVENT}" \
  --cli-binary-format raw-in-base64-out \
  --region "${REGION}" \
  "${RESPONSE_FILE}" \
  --output json > /dev/null 2>&1

# --- Step 2: Check response ---
echo "Step 2: Checking Lambda response..."
echo ""

if [[ ! -f "${RESPONSE_FILE}" ]]; then
  echo "ERROR: Response file not created"
  exit 1
fi

echo "Response:"
cat "${RESPONSE_FILE}"
echo ""
echo ""

# Parse statusCode from response
STATUS_CODE=$(python3 -c "
import json, sys
try:
    with open('${RESPONSE_FILE}') as f:
        resp = json.load(f)
    print(resp.get('statusCode', 'unknown'))
except Exception as e:
    print(f'error: {e}', file=sys.stderr)
    print('unknown')
" 2>/dev/null || echo "unknown")

if [[ "${STATUS_CODE}" == "200" ]]; then
  echo "✅ Lambda returned statusCode 200 — events shipped successfully"
elif [[ "${STATUS_CODE}" == "207" ]]; then
  echo "⚠️  Lambda returned statusCode 207 — partial success (some events may have failed)"
else
  echo "❌ Lambda returned unexpected statusCode: ${STATUS_CODE}"
  exit 1
fi

# --- Step 3: Check CloudWatch Logs ---
echo ""
echo "Step 3: Checking CloudWatch Logs (last 2 minutes)..."
echo ""

LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
echo "  Log group: ${LOG_GROUP}"
echo ""

# Try to get recent logs
LOGS=$(aws logs filter-log-events \
  --log-group-name "${LOG_GROUP}" \
  --start-time "$(python3 -c 'import time; print(int((time.time() - 120) * 1000))')" \
  --filter-pattern "Successfully shipped" \
  --region "${REGION}" \
  --query 'events[*].message' \
  --output text 2>/dev/null || echo "")

if [[ -n "${LOGS}" ]]; then
  echo "✅ Found 'Successfully shipped' in CloudWatch Logs"
  echo "  ${LOGS}" | head -3
else
  echo "⚠️  'Successfully shipped' not found in recent logs (may need more time)"
  echo "  Manual check: aws logs tail ${LOG_GROUP} --since 5m --region ${REGION}"
fi

# --- Step 4: Provide Splunk verification query ---
echo ""
echo "=== Next Steps ==="
echo ""
echo "Step 4: Verify in Splunk Search with the following SPL query:"
echo ""
echo "  index=fsxn_audit result=Failure earliest=-15m"
echo ""
echo "Expected: At least 1 event with result=Failure should appear."
echo ""
echo "Screenshot: Save as docs/screenshots/splunk/splunk-unauthorized-access-$(date +%Y%m%d).png"
echo ""

# Cleanup
rm -f "${RESPONSE_FILE}"

echo "=== Demo Scenario 1 Complete ==="
