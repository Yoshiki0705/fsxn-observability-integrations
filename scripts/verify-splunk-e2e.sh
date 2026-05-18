#!/usr/bin/env bash
# E2E verification orchestrator for the Splunk serverless integration.
# Validates CloudFormation stack, HEC token, invokes Lambda, checks
# CloudWatch Logs, provides SPL query, runs screenshot validation,
# bilingual comparison, and generates results document.
#
# Usage:
#   ./scripts/verify-splunk-e2e.sh \
#     --stack-name fsxn-splunk-integration \
#     --region ap-northeast-1
#
# Exit codes:
#   0 - All verification steps passed
#   1 - One or more verification steps failed

set -euo pipefail

# ─── Color output helpers ───────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

pass_msg() { echo -e "  ${GREEN}✔ PASS${NC}: $1"; }
fail_msg() { echo -e "  ${RED}✘ FAIL${NC}: $1"; }
skip_msg() { echo -e "  ${YELLOW}⏭ SKIP${NC}: $1"; }
info_msg() { echo -e "  ${YELLOW}ℹ${NC} $1"; }
header_msg() { echo -e "\n${BOLD}── $1 ──${NC}"; }

# ─── Defaults ───────────────────────────────────────────────────────────────

STACK_NAME="fsxn-splunk-integration"
REGION="ap-northeast-1"
TEST_EVENT="integrations/splunk-serverless/tests/test_data/sample_s3_event.json"
SCREENSHOTS_DIR="docs/screenshots/splunk"

# ─── Usage ──────────────────────────────────────────────────────────────────

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Runs end-to-end verification for the Splunk serverless integration.

Options:
  --stack-name NAME    CloudFormation stack name (default: fsxn-splunk-integration)
  --region REGION      AWS region (default: ap-northeast-1)
  --test-event PATH    Path to test event JSON file
  -h, --help           Show this help message

Exit Codes:
  0  All verification steps passed
  1  One or more verification steps failed

Examples:
  $(basename "$0")
  $(basename "$0") --stack-name my-stack --region us-east-1
  $(basename "$0") --test-event path/to/event.json
EOF
  exit 0
}

# ─── Argument parsing ───────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    -h|--help)
      usage
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      echo "Run '$(basename "$0") --help' for usage." >&2
      exit 1
      ;;
  esac
done

# ─── State tracking ────────────────────────────────────────────────────────

STEPS_TOTAL=9
STEPS_PASSED=0
STEPS_FAILED=0
STEPS_SKIPPED=0
TMPDIR_WORK=$(mktemp -d)

cleanup() {
  rm -rf "$TMPDIR_WORK"
}
trap cleanup EXIT

# ─── Pre-flight checks ─────────────────────────────────────────────────────

header_msg "Pre-flight checks"

if ! command -v aws &>/dev/null; then
  fail_msg "AWS CLI not found in PATH. Install it first."
  exit 1
fi
pass_msg "AWS CLI available"

if ! command -v jq &>/dev/null; then
  fail_msg "jq not found in PATH. Install it first."
  exit 1
fi
pass_msg "jq available"

if ! command -v python3 &>/dev/null; then
  fail_msg "python3 not found in PATH. Install it first."
  exit 1
fi
pass_msg "python3 available"

if [[ ! -f "$TEST_EVENT" ]]; then
  fail_msg "Test event file not found: $TEST_EVENT"
  exit 1
fi
pass_msg "Test event file exists: $TEST_EVENT"

# ─── Step 1: Validate CloudFormation stack status ───────────────────────────

step1_validate_stack() {
  header_msg "Step 1: Validate CloudFormation stack status"
  info_msg "Stack: $STACK_NAME | Region: $REGION"

  local stack_output
  if ! stack_output=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --output json 2>&1); then
    fail_msg "Failed to describe stack '$STACK_NAME' — is it deployed?"
    info_msg "Error: $stack_output"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local stack_status
  stack_status=$(echo "$stack_output" | jq -r '.Stacks[0].StackStatus')

  if [[ "$stack_status" == "CREATE_COMPLETE" || "$stack_status" == "UPDATE_COMPLETE" ]]; then
    pass_msg "Stack status: $stack_status"
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  else
    fail_msg "Stack status is '$stack_status' (expected CREATE_COMPLETE or UPDATE_COMPLETE)"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi
}

# ─── Step 2: Validate HEC token in Secrets Manager ─────────────────────────

step2_validate_hec_token() {
  header_msg "Step 2: Validate HEC token in Secrets Manager"

  # Retrieve the secret ARN from stack outputs or use convention
  local secret_name="splunk/fsxn-hec-token"
  info_msg "Secret name: $secret_name"

  local validation_output
  if ! validation_output=$(python3 -c "
import sys, json
sys.path.insert(0, '.')
from scripts.verification.splunk_token_validator import validate_hec_token

# Build ARN from secret name and region
secret_arn = 'arn:aws:secretsmanager:${REGION}:$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "000000000000"):secret:${secret_name}'

# Try with secret name first (simpler)
try:
    result = validate_hec_token('${secret_name}')
except Exception:
    result = validate_hec_token(secret_arn)

print(json.dumps({'status': result.status, 'error': result.error, 'token_format_valid': result.token_format_valid}))
sys.exit(0 if result.status == 'pass' else 1)
" 2>&1); then
    fail_msg "HEC token validation failed"
    info_msg "Output: $validation_output"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  pass_msg "HEC token is valid (UUID format confirmed)"
  info_msg "$validation_output"
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Step 3: Invoke Lambda with test event ──────────────────────────────────

step3_invoke_lambda() {
  header_msg "Step 3: Invoke Lambda with test event"

  local function_name="${STACK_NAME}-shipper"
  local response_file="${TMPDIR_WORK}/lambda-response.json"

  info_msg "Function: $function_name"
  info_msg "Payload: $TEST_EVENT"

  local invoke_output
  if ! invoke_output=$(aws lambda invoke \
    --function-name "$function_name" \
    --region "$REGION" \
    --payload "file://${TEST_EVENT}" \
    --cli-binary-format raw-in-base64-out \
    --cli-read-timeout 60 \
    "$response_file" 2>&1); then
    fail_msg "Lambda invocation failed"
    info_msg "Error: $invoke_output"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  # Check for function error
  local function_error
  function_error=$(echo "$invoke_output" | jq -r '.FunctionError // empty' 2>/dev/null || true)
  if [[ -n "$function_error" ]]; then
    fail_msg "Lambda returned FunctionError: $function_error"
    info_msg "Response: $(cat "$response_file" 2>/dev/null || echo 'N/A')"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  # Parse and validate response
  local response
  response=$(cat "$response_file")
  info_msg "Raw response: $(echo "$response" | head -c 500)"

  local status_code
  status_code=$(echo "$response" | jq -r '.statusCode // empty' 2>/dev/null || true)

  if [[ -z "$status_code" ]]; then
    fail_msg "Response missing 'statusCode' field"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local total_logs total_shipped
  if echo "$response" | jq -e '.body' &>/dev/null; then
    local body
    if echo "$response" | jq -e '.body | type == "string"' &>/dev/null 2>&1; then
      body=$(echo "$response" | jq -r '.body' | jq '.')
    else
      body=$(echo "$response" | jq '.body')
    fi
    total_logs=$(echo "$body" | jq -r '.total_logs // empty' 2>/dev/null || true)
    total_shipped=$(echo "$body" | jq -r '.total_shipped // empty' 2>/dev/null || true)
  else
    total_logs=$(echo "$response" | jq -r '.total_logs // empty' 2>/dev/null || true)
    total_shipped=$(echo "$response" | jq -r '.total_shipped // empty' 2>/dev/null || true)
  fi

  info_msg "statusCode: $status_code | total_logs: ${total_logs:-N/A} | total_shipped: ${total_shipped:-N/A}"

  if [[ "$status_code" == "200" || "$status_code" == "207" ]]; then
    pass_msg "Lambda invoked successfully (statusCode=$status_code, shipped=${total_shipped:-0})"
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  else
    fail_msg "Unexpected statusCode: $status_code"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi
}

# ─── Step 4: Check CloudWatch Logs ─────────────────────────────────────────

step4_check_cloudwatch_logs() {
  header_msg "Step 4: Check CloudWatch Logs for recent execution"

  local log_group="/aws/lambda/${STACK_NAME}-shipper"
  local now_ms=$(($(date +%s) * 1000))
  local five_min_ago_ms=$((($(date +%s) - 300) * 1000))

  info_msg "Log group: $log_group"
  info_msg "Time range: last 5 minutes"

  local log_output
  if ! log_output=$(aws logs filter-log-events \
    --log-group-name "$log_group" \
    --region "$REGION" \
    --start-time "$five_min_ago_ms" \
    --end-time "$now_ms" \
    --filter-pattern "Successfully shipped" \
    --limit 10 \
    --output json 2>&1); then
    fail_msg "Failed to query CloudWatch Logs"
    info_msg "Error: $log_output"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local event_count
  event_count=$(echo "$log_output" | jq '.events | length' 2>/dev/null || echo "0")

  if [[ "$event_count" -gt 0 ]]; then
    pass_msg "Found $event_count 'Successfully shipped' log event(s) in the last 5 minutes"
    info_msg "Latest log messages:"
    echo "$log_output" | jq -r '.events[-3:][].message' 2>/dev/null | while IFS= read -r line; do
      info_msg "  $line"
    done
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  else
    fail_msg "No 'Successfully shipped' log events found in the last 5 minutes"
    info_msg "The Lambda function may not have executed recently, or logs are delayed."
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi
}

# ─── Step 5: Provide SPL query for Splunk verification ──────────────────────

step5_provide_spl_query() {
  header_msg "Step 5: Splunk Search verification (SPL query)"

  info_msg "Run the following SPL query in Splunk Search to confirm log arrival:"
  echo ""
  echo -e "  ${BOLD}index=fsxn_audit sourcetype=fsxn:ontap:audit earliest=-15m${NC}"
  echo ""
  info_msg "Expected fields in results:"
  info_msg "  - host (non-empty): SVM name"
  info_msg "  - source (non-empty): fsxn-observability"
  info_msg "  - sourcetype (non-empty): fsxn:ontap:audit"
  info_msg "  - index (non-empty): fsxn_audit"
  info_msg "  - event.event_type (non-empty)"
  info_msg "  - event.user (non-empty)"
  info_msg "  - event.operation (non-empty)"
  info_msg "  - event.path (non-empty)"
  info_msg "  - event.result (non-empty)"
  info_msg "  - event.svm (non-empty)"
  echo ""
  info_msg "For EMS/ARP events:"
  echo -e "  ${BOLD}index=fsxn_ems sourcetype=fsxn:ontap:ems earliest=-15m${NC}"
  echo ""

  # This step always passes as it's informational
  pass_msg "SPL query provided for manual Splunk verification"
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Step 6: Send test EMS event (optional) ─────────────────────────────────

step6_ems_test() {
  header_msg "Step 6: Send test EMS event (optional)"

  # Attempt to retrieve the EMS API Gateway endpoint from stack outputs
  local ems_endpoint
  ems_endpoint=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='EmsApiEndpoint'].OutputValue" \
    --output text 2>/dev/null || true)

  if [[ -z "$ems_endpoint" || "$ems_endpoint" == "None" ]]; then
    skip_msg "EMS API endpoint not found in stack outputs — EMS stack may not be deployed"
    info_msg "To enable this step, deploy the EMS webhook stack and ensure 'EmsApiEndpoint' is in stack outputs."
    STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
    return 0
  fi

  info_msg "EMS API endpoint: $ems_endpoint"

  # Retrieve EMS API key from Secrets Manager (optional)
  local ems_api_key
  ems_api_key=$(aws secretsmanager get-secret-value \
    --secret-id "splunk/fsxn-ems-api-key" \
    --region "$REGION" \
    --query "SecretString" \
    --output text 2>/dev/null || true)

  if [[ -z "$ems_api_key" ]]; then
    skip_msg "EMS API key not found in Secrets Manager (splunk/fsxn-ems-api-key) — skipping EMS test"
    STEPS_SKIPPED=$((STEPS_SKIPPED + 1))
    return 0
  fi

  # Build sample arw.volume.state EMS event payload
  local ems_payload
  ems_payload=$(cat <<'EMSJSON'
{
  "message-name": "arw.volume.state",
  "message-severity": "alert",
  "message-timestamp": "TIMESTAMP_PLACEHOLDER",
  "parameters": {
    "volume-name": "vol_data",
    "vserver-name": "svm-prod-01",
    "state": "attack-detected",
    "attack-type": "ransomware",
    "suspect-files-count": "12",
    "snapshot-name": "Anti_ransomware_backup",
    "description": "E2E verification test: ARP detection event"
  }
}
EMSJSON
)

  # Replace timestamp placeholder with current time
  local current_ts
  current_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  ems_payload=$(echo "$ems_payload" | sed "s/TIMESTAMP_PLACEHOLDER/$current_ts/")

  info_msg "Sending arw.volume.state EMS event to API Gateway..."

  local http_code
  local response_body="${TMPDIR_WORK}/ems-response.json"

  http_code=$(curl -s -o "$response_body" -w "%{http_code}" \
    -X POST "$ems_endpoint" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $ems_api_key" \
    -d "$ems_payload" \
    --connect-timeout 10 \
    --max-time 30 2>/dev/null || echo "000")

  if [[ "$http_code" == "000" ]]; then
    fail_msg "Failed to connect to EMS API endpoint (timeout or network error)"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  info_msg "HTTP response code: $http_code"
  info_msg "Response body: $(cat "$response_body" 2>/dev/null | head -c 300)"

  if [[ "$http_code" == "200" ]]; then
    pass_msg "EMS test event accepted by API Gateway (HTTP 200)"
    info_msg "Event: arw.volume.state (ARP ransomware detection)"
    info_msg "Verify in Splunk: index=fsxn_ems sourcetype=fsxn:ontap:ems message-name=arw.volume.state"
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  elif [[ "$http_code" == "401" ]]; then
    fail_msg "EMS API key authentication failed (HTTP 401)"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  else
    fail_msg "EMS test event failed with HTTP $http_code"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi
}

# ─── Step 7: Run screenshot validation ──────────────────────────────────────

step7_screenshot_validation() {
  header_msg "Step 7: Run screenshot validation"

  info_msg "Screenshots directory: $SCREENSHOTS_DIR"

  if [[ ! -d "$SCREENSHOTS_DIR" ]]; then
    fail_msg "Screenshots directory not found: $SCREENSHOTS_DIR"
    info_msg "Create the directory and add required screenshots before running verification."
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local validation_output
  if ! validation_output=$(python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.verification.splunk_screenshot_validator import validate_screenshots
results = validate_screenshots('${SCREENSHOTS_DIR}')
pass_count = sum(1 for r in results if r.result == 'pass')
fail_count = sum(1 for r in results if r.result == 'fail')
for r in results:
    icon = '✔ PASS' if r.result == 'pass' else '✘ FAIL'
    print(f'  {icon}: {r.step_name}')
    if r.output and r.result == 'fail':
        print(f'    Detail: {r.output}')
print(f'  Summary: {pass_count} passed, {fail_count} failed')
sys.exit(0 if fail_count == 0 else 1)
" 2>&1); then
    fail_msg "Screenshot validation failed"
    echo "$validation_output" | while IFS= read -r line; do
      info_msg "$line"
    done
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  pass_msg "All screenshots validated"
  echo "$validation_output" | while IFS= read -r line; do
    info_msg "$line"
  done
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Step 8: Run bilingual comparison ───────────────────────────────────────

step8_bilingual_comparison() {
  header_msg "Step 8: Run bilingual comparison"

  local ja_path="integrations/splunk-serverless/docs/ja/setup-guide.md"
  local en_path="integrations/splunk-serverless/docs/en/setup-guide.md"

  info_msg "JA: $ja_path"
  info_msg "EN: $en_path"

  if [[ ! -f "$ja_path" ]]; then
    fail_msg "Japanese setup guide not found: $ja_path"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  if [[ ! -f "$en_path" ]]; then
    fail_msg "English setup guide not found: $en_path"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local comparison_output
  if ! comparison_output=$(python3 scripts/compare-bilingual.py \
    --ja "$ja_path" \
    --en "$en_path" 2>&1); then
    fail_msg "Bilingual comparison failed"
    echo "$comparison_output" | while IFS= read -r line; do
      info_msg "  $line"
    done
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  pass_msg "Bilingual comparison passed (heading structure and code blocks match)"
  echo "$comparison_output" | while IFS= read -r line; do
    info_msg "  $line"
  done
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Step 9: Generate results document ─────────────────────────────────────

step9_generate_results() {
  header_msg "Step 9: Generate results document"

  local output_path="docs/ja/verification-results-splunk.md"
  local verifier_name
  verifier_name="$(whoami)"

  info_msg "Verifier: $verifier_name"
  info_msg "Region: $REGION"
  info_msg "Stack: $STACK_NAME"
  info_msg "Output: $output_path"

  local generate_output
  if ! generate_output=$(python3 scripts/generate-results.py \
    --verifier-name "$verifier_name" \
    --region "$REGION" \
    --stack-name "$STACK_NAME" \
    --screenshots-dir "$SCREENSHOTS_DIR" \
    --ja integrations/splunk-serverless/docs/ja/setup-guide.md \
    --en integrations/splunk-serverless/docs/en/setup-guide.md \
    --output "$output_path" 2>&1); then
    fail_msg "Results document generation failed"
    info_msg "Output:"
    echo "$generate_output" | while IFS= read -r line; do
      info_msg "  $line"
    done
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  pass_msg "Results document generated: $output_path"
  echo "$generate_output" | while IFS= read -r line; do
    info_msg "  $line"
  done
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Main execution ────────────────────────────────────────────────────────

main() {
  echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   Splunk E2E Verification — FSxN Observability          ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
  echo ""
  info_msg "Stack:      $STACK_NAME"
  info_msg "Region:     $REGION"
  info_msg "Test Event: $TEST_EVENT"

  # Run each step; continue on failure to report all results
  step1_validate_stack || true
  step2_validate_hec_token || true
  step3_invoke_lambda || true
  step4_check_cloudwatch_logs || true
  step5_provide_spl_query || true
  step6_ems_test || true
  step7_screenshot_validation || true
  step8_bilingual_comparison || true
  step9_generate_results || true

  # ─── Summary ────────────────────────────────────────────────────────────
  header_msg "Summary"
  echo ""
  echo -e "  Total steps: ${STEPS_TOTAL}"
  echo -e "  ${GREEN}Passed${NC}:     ${STEPS_PASSED}"
  echo -e "  ${RED}Failed${NC}:     ${STEPS_FAILED}"
  echo -e "  ${YELLOW}Skipped${NC}:    ${STEPS_SKIPPED}"
  echo ""

  if [[ "$STEPS_FAILED" -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}All verification steps passed ✔${NC}"
    echo ""
    return 0
  else
    echo -e "  ${RED}${BOLD}One or more verification steps failed ✘${NC}"
    echo ""
    return 1
  fi
}

main
