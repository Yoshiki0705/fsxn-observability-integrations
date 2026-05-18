#!/usr/bin/env bash
set -euo pipefail

# ─── OTel Collector E2E Verification Script ─────────────────────────────────
# Validates the full pipeline: Lambda → OTel Collector → Backends
#
# Usage:
#   ./scripts/verify-otel-e2e.sh --stack-name fsxn-otel-integration --region ap-northeast-1
#   ./scripts/verify-otel-e2e.sh --stack-name fsxn-otel-integration --region ap-northeast-1 --test-event path/to/event.json

STACK_NAME=""
REGION="ap-northeast-1"
TEST_EVENT="integrations/otel-collector/tests/test_data/sample_s3_event.json"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --stack-name)
      STACK_NAME="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --test-event)
      TEST_EVENT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$STACK_NAME" ]]; then
  echo "Error: --stack-name is required"
  echo "Usage: $0 --stack-name <name> [--region <region>] [--test-event <path>]"
  exit 1
fi

echo "═══════════════════════════════════════════════════════════════"
echo "  OTel Collector E2E Verification"
echo "  Stack: $STACK_NAME"
echo "  Region: $REGION"
echo "═══════════════════════════════════════════════════════════════"
echo ""

PASS=0
FAIL=0

check() {
  local description="$1"
  local result="$2"
  if [[ "$result" == "0" ]]; then
    echo "  ✅ $description"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $description"
    FAIL=$((FAIL + 1))
  fi
}

# ─── Step 1: Validate stack status ──────────────────────────────────────────
echo "Step 1: Validating CloudFormation stack status..."
STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || echo "FAILED")

if [[ "$STACK_STATUS" == *"COMPLETE"* ]]; then
  check "Stack status is $STACK_STATUS" "0"
else
  check "Stack status is $STACK_STATUS (expected *COMPLETE*)" "1"
fi

# Get Lambda function name from stack outputs
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" \
  --output text 2>/dev/null || echo "")

if [[ -z "$FUNCTION_NAME" ]]; then
  FUNCTION_NAME="${STACK_NAME}-shipper"
fi

echo ""

# ─── Step 2: Invoke Lambda with test event ───────────────────────────────────
echo "Step 2: Invoking Lambda with test event..."
RESPONSE_FILE=$(mktemp)

INVOKE_STATUS=$(aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --payload "file://$TEST_EVENT" \
  --cli-binary-format raw-in-base64-out \
  "$RESPONSE_FILE" \
  --query "StatusCode" \
  --output text 2>/dev/null || echo "999")

if [[ "$INVOKE_STATUS" == "200" ]]; then
  check "Lambda invocation returned HTTP 200" "0"
else
  check "Lambda invocation returned HTTP $INVOKE_STATUS" "1"
fi

# ─── Step 3: Parse Lambda response ──────────────────────────────────────────
echo ""
echo "Step 3: Parsing Lambda response..."

if [[ -f "$RESPONSE_FILE" ]]; then
  STATUS_CODE=$(python3 -c "import json; print(json.load(open('$RESPONSE_FILE'))['statusCode'])" 2>/dev/null || echo "0")
  TOTAL_SHIPPED=$(python3 -c "import json; print(json.load(open('$RESPONSE_FILE'))['body']['total_shipped'])" 2>/dev/null || echo "0")
  TOTAL_LOGS=$(python3 -c "import json; print(json.load(open('$RESPONSE_FILE'))['body']['total_logs'])" 2>/dev/null || echo "0")

  if [[ "$STATUS_CODE" == "200" ]]; then
    check "Response statusCode is 200" "0"
  else
    check "Response statusCode is $STATUS_CODE (expected 200)" "1"
  fi

  if [[ "$TOTAL_SHIPPED" -gt "0" ]]; then
    check "total_shipped = $TOTAL_SHIPPED (> 0)" "0"
  else
    check "total_shipped = $TOTAL_SHIPPED (expected > 0)" "1"
  fi

  echo "  ℹ️  total_logs=$TOTAL_LOGS, total_shipped=$TOTAL_SHIPPED"
fi

rm -f "$RESPONSE_FILE"

# ─── Step 4: Check CloudWatch Logs ──────────────────────────────────────────
echo ""
echo "Step 4: Checking CloudWatch Logs for OTLP export success..."

LOG_GROUP="/aws/lambda/$FUNCTION_NAME"
RECENT_LOGS=$(aws logs filter-log-events \
  --log-group-name "$LOG_GROUP" \
  --region "$REGION" \
  --start-time $(($(date +%s) * 1000 - 300000)) \
  --filter-pattern "OTLP payload sent successfully" \
  --query "events[0].message" \
  --output text 2>/dev/null || echo "NONE")

if [[ "$RECENT_LOGS" != "NONE" && "$RECENT_LOGS" != "None" ]]; then
  check "CloudWatch Logs show OTLP delivery success" "0"
else
  check "CloudWatch Logs show OTLP delivery success" "1"
fi

# ─── Step 5: Health check endpoint ──────────────────────────────────────────
echo ""
echo "Step 5: Verifying OTel Collector health check (if accessible)..."

HEALTH_STATUS=$(curl -sf http://localhost:13133/ 2>/dev/null && echo "OK" || echo "UNREACHABLE")

if [[ "$HEALTH_STATUS" == "OK" ]]; then
  check "OTel Collector health check (localhost:13133)" "0"
else
  echo "  ⚠️  OTel Collector health check not reachable (expected if running remotely)"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════════════════════"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
