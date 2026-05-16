#!/usr/bin/env bash
# E2E verification orchestrator for the Datadog integration.
# Validates CloudFormation stack, invokes Lambda, parses response,
# and checks CloudWatch Logs for recent execution.
#
# Usage:
#   ./scripts/verify-datadog-e2e.sh \
#     --stack-name fsxn-datadog-integration \
#     --region ap-northeast-1 \
#     --test-event integrations/datadog/tests/test_data/sample_s3_event.json
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
info_msg() { echo -e "  ${YELLOW}ℹ${NC} $1"; }
header_msg() { echo -e "\n${BOLD}── $1 ──${NC}"; }

# ─── Defaults ───────────────────────────────────────────────────────────────

STACK_NAME="fsxn-datadog-integration"
REGION="ap-northeast-1"
TEST_EVENT="integrations/datadog/tests/test_data/sample_s3_event.json"

# ─── Usage ──────────────────────────────────────────────────────────────────

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Runs end-to-end verification for the Datadog integration.

Options:
  --stack-name NAME    CloudFormation stack name (default: fsxn-datadog-integration)
  --region REGION      AWS region (default: ap-northeast-1)
  --test-event PATH    Path to test event JSON file (default: integrations/datadog/tests/test_data/sample_s3_event.json)
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

STEPS_TOTAL=7
STEPS_PASSED=0
STEPS_FAILED=0
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

# ─── Step 2: Invoke Lambda with test event ──────────────────────────────────

step2_invoke_lambda() {
  header_msg "Step 2: Invoke Lambda with test event"

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

  pass_msg "Lambda invoked successfully"
  STEPS_PASSED=$((STEPS_PASSED + 1))

  # Store response for Step 3
  cp "$response_file" "${TMPDIR_WORK}/response-for-parse.json"
  return 0
}

# ─── Step 3: Parse Lambda response ─────────────────────────────────────────

step3_parse_response() {
  header_msg "Step 3: Parse Lambda response"

  local response_file="${TMPDIR_WORK}/response-for-parse.json"

  if [[ ! -f "$response_file" ]]; then
    fail_msg "No response file from Step 2 — skipping"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local response
  response=$(cat "$response_file")
  info_msg "Raw response: $(echo "$response" | head -c 500)"

  # Parse statusCode (may be top-level or nested in body)
  local status_code
  status_code=$(echo "$response" | jq -r '.statusCode // empty' 2>/dev/null || true)

  if [[ -z "$status_code" ]]; then
    fail_msg "Response missing 'statusCode' field"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  info_msg "statusCode: $status_code"

  # Parse body fields
  local total_logs total_shipped errors_count

  # Try body as nested object first, then top-level
  if echo "$response" | jq -e '.body' &>/dev/null; then
    local body
    # body might be a string (JSON-encoded) or an object
    if echo "$response" | jq -e '.body | type == "string"' &>/dev/null 2>&1; then
      body=$(echo "$response" | jq -r '.body' | jq '.')
    else
      body=$(echo "$response" | jq '.body')
    fi
    total_logs=$(echo "$body" | jq -r '.total_logs // empty' 2>/dev/null || true)
    total_shipped=$(echo "$body" | jq -r '.total_shipped // empty' 2>/dev/null || true)
    errors_count=$(echo "$body" | jq -r '.errors | length' 2>/dev/null || echo "0")
  else
    total_logs=$(echo "$response" | jq -r '.total_logs // empty' 2>/dev/null || true)
    total_shipped=$(echo "$response" | jq -r '.total_shipped // empty' 2>/dev/null || true)
    errors_count=$(echo "$response" | jq -r '.errors | length' 2>/dev/null || echo "0")
  fi

  info_msg "total_logs: ${total_logs:-N/A}"
  info_msg "total_shipped: ${total_shipped:-N/A}"
  info_msg "errors: ${errors_count}"

  # Validate response
  local step_passed=true

  if [[ "$status_code" != "200" && "$status_code" != "207" ]]; then
    fail_msg "Unexpected statusCode: $status_code (expected 200 or 207)"
    step_passed=false
  fi

  if [[ -z "$total_logs" ]]; then
    fail_msg "Missing 'total_logs' in response"
    step_passed=false
  elif [[ "$total_logs" -lt 1 ]] 2>/dev/null; then
    fail_msg "total_logs is $total_logs (expected >= 1)"
    step_passed=false
  fi

  if [[ -z "$total_shipped" ]]; then
    fail_msg "Missing 'total_shipped' in response"
    step_passed=false
  elif [[ "$total_shipped" -lt 1 ]] 2>/dev/null; then
    fail_msg "total_shipped is $total_shipped (expected >= 1)"
    step_passed=false
  fi

  if [[ "$errors_count" -gt 0 ]]; then
    fail_msg "Response contains $errors_count error(s)"
    if echo "$response" | jq -e '.body.errors' &>/dev/null 2>&1; then
      info_msg "Errors: $(echo "$response" | jq -c '.body.errors')"
    elif echo "$response" | jq -e '.errors' &>/dev/null 2>&1; then
      info_msg "Errors: $(echo "$response" | jq -c '.errors')"
    fi
    # statusCode 207 with errors is acceptable (partial success)
    if [[ "$status_code" == "207" ]]; then
      info_msg "statusCode 207 indicates partial success — continuing"
    else
      step_passed=false
    fi
  fi

  if [[ "$step_passed" == "true" ]]; then
    pass_msg "Response validation passed (statusCode=$status_code, logs=$total_logs, shipped=$total_shipped)"
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  else
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
    --limit 20 \
    --output json 2>&1); then
    fail_msg "Failed to query CloudWatch Logs"
    info_msg "Error: $log_output"
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local event_count
  event_count=$(echo "$log_output" | jq '.events | length' 2>/dev/null || echo "0")

  if [[ "$event_count" -gt 0 ]]; then
    pass_msg "Found $event_count log event(s) in the last 5 minutes"
    info_msg "Latest log messages:"
    echo "$log_output" | jq -r '.events[-3:][].message' 2>/dev/null | while IFS= read -r line; do
      info_msg "  $line"
    done
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  else
    fail_msg "No log events found in the last 5 minutes"
    info_msg "The Lambda function may not have executed recently, or logs are delayed."
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi
}

# ─── Step 5: Run bilingual comparison ───────────────────────────────────────

step5_bilingual_comparison() {
  header_msg "Step 5: Run bilingual comparison"

  local ja_path="integrations/datadog/docs/ja/setup-guide.md"
  local en_path="integrations/datadog/docs/en/setup-guide.md"

  info_msg "JA: $ja_path"
  info_msg "EN: $en_path"

  local comparison_output
  if ! comparison_output=$(python3 scripts/compare-bilingual.py \
    --ja "$ja_path" \
    --en "$en_path" 2>&1); then
    fail_msg "Bilingual comparison failed"
    info_msg "Output:"
    echo "$comparison_output" | while IFS= read -r line; do
      info_msg "  $line"
    done
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  pass_msg "Bilingual comparison passed"
  echo "$comparison_output" | while IFS= read -r line; do
    info_msg "  $line"
  done
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Step 6: Run screenshot validation ──────────────────────────────────────

step6_screenshot_validation() {
  header_msg "Step 6: Run screenshot validation"

  local screenshots_dir="docs/screenshots"
  info_msg "Screenshots directory: $screenshots_dir"

  local validation_output
  if ! validation_output=$(python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.verification.screenshot_validator import validate_screenshots
results = validate_screenshots('$screenshots_dir')
for r in results:
    status = '✔ PASS' if r.result == 'success' else '✘ FAIL'
    print(f'  {status}: {r.step_name}')
    if r.error_detail:
        print(f'    Error: {r.error_detail}')
sys.exit(0 if all(r.result == 'success' for r in results) else 1)
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

# ─── Step 7: Generate results document ─────────────────────────────────────

step7_generate_results() {
  header_msg "Step 7: Generate results document"

  local output_path="docs/ja/verification-results-datadog.md"
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
    --screenshots-dir docs/screenshots \
    --ja integrations/datadog/docs/ja/setup-guide.md \
    --en integrations/datadog/docs/en/setup-guide.md \
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
  echo -e "${BOLD}║   Datadog E2E Verification — FSxN Observability         ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
  echo ""
  info_msg "Stack:      $STACK_NAME"
  info_msg "Region:     $REGION"
  info_msg "Test Event: $TEST_EVENT"

  # Run each step; continue on failure to report all results
  step1_validate_stack || true
  step2_invoke_lambda || true
  step3_parse_response || true
  step4_check_cloudwatch_logs || true
  step5_bilingual_comparison || true
  step6_screenshot_validation || true
  step7_generate_results || true

  # ─── Summary ────────────────────────────────────────────────────────────
  header_msg "Summary"
  echo ""
  echo -e "  Total steps: ${STEPS_TOTAL}"
  echo -e "  ${GREEN}Passed${NC}:     ${STEPS_PASSED}"
  echo -e "  ${RED}Failed${NC}:     ${STEPS_FAILED}"
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
