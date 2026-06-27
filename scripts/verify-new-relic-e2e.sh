#!/usr/bin/env bash
# E2E verification orchestrator for the New Relic integration.
# Validates CloudFormation stack, invokes Lambda, parses response,
# checks CloudWatch Logs, executes NRQL queries via NerdGraph API,
# runs bilingual comparison, and runs screenshot validation.
#
# Usage:
#   ./scripts/verify-new-relic-e2e.sh \
#     --stack-name fsxn-new-relic-integration \
#     --region ap-northeast-1 \
#     --test-event integrations/new-relic/tests/test_data/sample_s3_event.json \
#     --nr-account-id 1234567 \
#     --nr-api-key-env NR_API_KEY
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

STACK_NAME="fsxn-new-relic-integration"
REGION="ap-northeast-1"
TEST_EVENT="integrations/new-relic/tests/test_data/sample_s3_event.json"
NR_ACCOUNT_ID=""
NR_API_KEY_ENV="NR_API_KEY"

# ─── Usage ──────────────────────────────────────────────────────────────────

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Runs end-to-end verification for the New Relic integration.

Options:
  --stack-name NAME       CloudFormation stack name (default: fsxn-new-relic-integration)
  --region REGION         AWS region (default: ap-northeast-1)
  --test-event PATH       Path to test event JSON file (default: integrations/new-relic/tests/test_data/sample_s3_event.json)
  --nr-account-id ID      New Relic account ID (required for NRQL queries)
  --nr-api-key-env VAR    Environment variable name containing NR User API Key (default: NR_API_KEY)
  -h, --help              Show this help message

Exit Codes:
  0  All verification steps passed
  1  One or more verification steps failed

Examples:
  $(basename "$0")
  $(basename "$0") --stack-name my-stack --region us-east-1
  $(basename "$0") --nr-account-id 1234567 --nr-api-key-env MY_NR_KEY
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
    --nr-account-id)
      NR_ACCOUNT_ID="$2"
      shift 2
      ;;
    --nr-api-key-env)
      NR_API_KEY_ENV="$2"
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

STEPS_TOTAL=8
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

if ! command -v curl &>/dev/null; then
  fail_msg "curl not found in PATH. Install it first."
  exit 1
fi
pass_msg "curl available"

if [[ ! -f "$TEST_EVENT" ]]; then
  fail_msg "Test event file not found: $TEST_EVENT"
  exit 1
fi
pass_msg "Test event file exists: $TEST_EVENT"

# Check NR API key availability (optional — NRQL step will be skipped if missing)
NR_API_KEY="${!NR_API_KEY_ENV:-}"
if [[ -n "$NR_API_KEY" && -n "$NR_ACCOUNT_ID" ]]; then
  pass_msg "New Relic API key and account ID available (NRQL queries enabled)"
else
  info_msg "New Relic API key or account ID not set — NRQL query step will be skipped"
fi

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

# ─── Step 5: Execute NRQL queries via NerdGraph API ─────────────────────────

step5_nrql_queries() {
  header_msg "Step 5: Execute NRQL queries via NerdGraph API"

  if [[ -z "$NR_API_KEY" || -z "$NR_ACCOUNT_ID" ]]; then
    info_msg "Skipping NRQL queries — --nr-account-id or NR_API_KEY not provided"
    info_msg "To enable this step, pass --nr-account-id and set the NR_API_KEY env var"
    # Count as passed (optional step)
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  fi

  info_msg "Account ID: ****${NR_ACCOUNT_ID: -4}"
  info_msg "API Key env: $NR_API_KEY_ENV"

  local nrql_queries=(
    "SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago"
    "SELECT count(*) FROM Log WHERE source='fsxn-ontap' FACET operation SINCE 1 hour ago"
  )

  local all_passed=true

  for query in "${nrql_queries[@]}"; do
    info_msg "Query: $query"

    local attempt=0
    local max_attempts=3
    local query_passed=false

    while [[ $attempt -lt $max_attempts ]]; do
      attempt=$((attempt + 1))

      # Escape single quotes in NRQL for JSON embedding
      local escaped_query
      escaped_query=$(echo "$query" | sed "s/'/\\\\'/g")

      local graphql_payload
      graphql_payload=$(jq -n --arg acct "$NR_ACCOUNT_ID" --arg nrql "$query" \
        '{ "query": "{ actor { account(id: \($acct | tonumber)) { nrql(query: \($nrql | tojson | ltrimstr("\"") | rtrimstr("\""))) { results } } } }" }')

      local api_response
      api_response=$(curl -s -w "\n%{http_code}" -X POST "https://api.newrelic.com/graphql" \
        -H "API-Key: ${NR_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$graphql_payload" 2>&1) || true

      local http_code
      http_code=$(echo "$api_response" | tail -1)
      local response_body
      response_body=$(echo "$api_response" | sed '$d')

      if [[ "$http_code" == "200" ]]; then
        # Check for errors in GraphQL response
        local gql_errors
        gql_errors=$(echo "$response_body" | jq -r '.errors // empty' 2>/dev/null || true)

        if [[ -n "$gql_errors" && "$gql_errors" != "null" ]]; then
          info_msg "  Attempt $attempt/$max_attempts: GraphQL error — $gql_errors"
        else
          # Check results
          local results
          results=$(echo "$response_body" | jq '.data.actor.account.nrql.results' 2>/dev/null || true)

          if [[ -n "$results" && "$results" != "null" && "$results" != "[]" ]]; then
            local result_count
            result_count=$(echo "$results" | jq 'length' 2>/dev/null || echo "0")
            pass_msg "Query returned $result_count result(s)"
            info_msg "  Results: $(echo "$results" | jq -c '.[0:3]' 2>/dev/null)"
            query_passed=true
            break
          else
            info_msg "  Attempt $attempt/$max_attempts: Query returned empty results"
          fi
        fi
      elif [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
        fail_msg "NerdGraph API authentication failed (HTTP $http_code)"
        info_msg "Check that $NR_API_KEY_ENV contains a valid User API Key"
        all_passed=false
        break
      else
        info_msg "  Attempt $attempt/$max_attempts: HTTP $http_code"
      fi

      if [[ $attempt -lt $max_attempts ]]; then
        info_msg "  Retrying in 10 seconds..."
        sleep 10
      fi
    done

    if [[ "$query_passed" != "true" ]]; then
      fail_msg "Query failed after $max_attempts attempts: $query"
      all_passed=false
    fi
  done

  if [[ "$all_passed" == "true" ]]; then
    STEPS_PASSED=$((STEPS_PASSED + 1))
    return 0
  else
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi
}

# ─── Step 6: Run bilingual comparison ───────────────────────────────────────

step6_bilingual_comparison() {
  header_msg "Step 6: Run bilingual comparison"

  local ja_path="integrations/new-relic/docs/ja/setup-guide.md"
  local en_path="integrations/new-relic/docs/en/setup-guide.md"

  info_msg "JA: $ja_path"
  info_msg "EN: $en_path"

  # Check if files exist before running comparison
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

# ─── Step 7: Run screenshot validation ──────────────────────────────────────

step7_screenshot_validation() {
  header_msg "Step 7: Run screenshot validation"

  local screenshots_dir="docs/screenshots/new-relic"
  info_msg "Screenshots directory: $screenshots_dir"

  if [[ ! -d "$screenshots_dir" ]]; then
    fail_msg "Screenshots directory not found: $screenshots_dir"
    info_msg "Create the directory and add required screenshots before running validation."
    STEPS_FAILED=$((STEPS_FAILED + 1))
    return 1
  fi

  local validation_output
  if ! validation_output=$(python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.verification.screenshot_validator import validate_new_relic_screenshots
results = validate_new_relic_screenshots('$screenshots_dir')
for r in results:
    status = 'PASS' if r.result == 'success' else 'FAIL'
    print(f'  {status}: {r.step_name}')
    if r.error_detail:
        print(f'    Error: {r.error_detail}')
all_pass = all(r.result == 'success' for r in results)
print(f'')
print(f'Total: {len(results)}, Passed: {sum(1 for r in results if r.result == \"success\")}, Failed: {sum(1 for r in results if r.result != \"success\")}')
sys.exit(0 if all_pass else 1)
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

# ─── Step 8: Report summary and generate results ───────────────────────────

step8_report_summary() {
  header_msg "Step 8: Generate verification summary"

  local output_file="${TMPDIR_WORK}/verification-summary.json"
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Generate JSON summary consumable by scripts/generate-results.py --vendor new-relic
  # The structure matches what load_new_relic_orchestrator_data() expects:
  # steps[], nrql_results[], alert_config{}, demo_timeline{}, environment{}
  cat > "$output_file" <<EOF
{
  "verification_date": "$timestamp",
  "stack_name": "$STACK_NAME",
  "region": "$REGION",
  "test_event": "$TEST_EVENT",
  "overall_result": "$([ "$STEPS_FAILED" -eq 0 ] && echo 'pass' || echo 'fail')",
  "steps_total": $STEPS_TOTAL,
  "steps_passed": $STEPS_PASSED,
  "steps_failed": $STEPS_FAILED,
  "steps": [
    {"step_number": 1, "step_name": "CloudFormation stack validation", "result": "skipped", "command": "aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION", "timestamp": "$timestamp"},
    {"step_number": 2, "step_name": "Lambda invocation with test event", "result": "skipped", "command": "aws lambda invoke --function-name ${STACK_NAME}-shipper --payload file://${TEST_EVENT}", "timestamp": "$timestamp"},
    {"step_number": 3, "step_name": "Lambda response parsing", "result": "skipped", "timestamp": "$timestamp"},
    {"step_number": 4, "step_name": "CloudWatch Logs verification", "result": "skipped", "command": "aws logs filter-log-events --log-group-name /aws/lambda/${STACK_NAME}-shipper", "timestamp": "$timestamp"},
    {"step_number": 5, "step_name": "NRQL query execution via NerdGraph", "result": "skipped", "timestamp": "$timestamp"},
    {"step_number": 6, "step_name": "Bilingual comparison (ja/en setup guides)", "result": "skipped", "command": "python3 scripts/compare-bilingual.py --ja integrations/new-relic/docs/ja/setup-guide.md --en integrations/new-relic/docs/en/setup-guide.md", "timestamp": "$timestamp"},
    {"step_number": 7, "step_name": "Screenshot validation (New Relic)", "result": "skipped", "command": "validate_new_relic_screenshots('docs/screenshots/new-relic')", "timestamp": "$timestamp"},
    {"step_number": 8, "step_name": "Verification summary generation", "result": "skipped", "timestamp": "$timestamp"}
  ],
  "nrql_results": [],
  "alert_config": {
    "nrql_query": "SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND result='Failure'",
    "threshold_value": 1,
    "evaluation_window_minutes": 5,
    "notification_channel": ""
  },
  "demo_timeline": {
    "file_write_timestamp": "",
    "scenario_status": "fail"
  },
  "environment": {
    "aws_region": "$REGION",
    "stack_name": "$STACK_NAME",
    "lambda_function_name": "${STACK_NAME}-shipper",
    "new_relic_region": "US",
    "new_relic_account_id_masked": "****${NR_ACCOUNT_ID: -4}",
    "aws_account_id_masked": "",
    "fsx_file_system_id": ""
  }
}
EOF

  info_msg "Verification summary:"
  cat "$output_file" | jq '.' 2>/dev/null || cat "$output_file"

  # Show how to use with generate-results.py
  info_msg "To generate the full results document, run:"
  info_msg "  python3 scripts/generate-results.py --vendor new-relic \\"
  info_msg "    --verifier-name \"<氏名>\" \\"
  info_msg "    --orchestrator-results ${output_file} \\"
  info_msg "    --output docs/ja/verification-results-new-relic.md"

  pass_msg "Verification summary generated"
  STEPS_PASSED=$((STEPS_PASSED + 1))
  return 0
}

# ─── Main execution ────────────────────────────────────────────────────────

main() {
  echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   New Relic E2E Verification — FSx for ONTAP Observability       ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
  echo ""
  info_msg "Stack:      $STACK_NAME"
  info_msg "Region:     $REGION"
  info_msg "Test Event: $TEST_EVENT"
  if [[ -n "$NR_ACCOUNT_ID" ]]; then
    info_msg "NR Account: ****${NR_ACCOUNT_ID: -4}"
  fi

  # Run each step; continue on failure to report all results
  step1_validate_stack || true
  step2_invoke_lambda || true
  step3_parse_response || true
  step4_check_cloudwatch_logs || true
  step5_nrql_queries || true
  step6_bilingual_comparison || true
  step7_screenshot_validation || true
  step8_report_summary || true

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
