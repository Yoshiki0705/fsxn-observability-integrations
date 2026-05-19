#!/usr/bin/env bash
# =============================================================================
# verify-splunk-account.sh
# =============================================================================
# Splunk アカウントと HEC エンドポイントの接続確認スクリプト
#
# Usage:
#   ./verify-splunk-account.sh
#
# Environment Variables:
#   SPLUNK_HEC_ENDPOINT  - Splunk HEC endpoint URL (e.g., https://your-instance:8088)
#
# This script:
#   1. Documents the steps to verify Splunk account access
#   2. Checks if SPLUNK_HEC_ENDPOINT environment variable is set
#   3. If set, attempts to reach the HEC health endpoint
#   4. Prints instructions for manual verification if not reachable
#
# Requirements: 1.1 (HEC トークン管理と Secrets Manager 登録)
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${BLUE}=============================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}=============================================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[STEP $1]${NC} $2"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# -----------------------------------------------------------------------------
# Main verification flow
# -----------------------------------------------------------------------------

print_header "Splunk Account & HEC Endpoint Verification"

echo "This script verifies that your Splunk account is accessible and the"
echo "HTTP Event Collector (HEC) endpoint is reachable."
echo ""
echo "Date: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Document manual verification steps
# ─────────────────────────────────────────────────────────────────────────────

print_step "1" "Splunk Account Verification Checklist"
echo ""
echo "  Before running this script, ensure the following:"
echo ""
echo "  □ You have a Splunk Cloud free trial or existing Splunk Enterprise account"
echo "    - Splunk Cloud Trial: https://www.splunk.com/en_us/download.html"
echo "    - Splunk Enterprise Trial: https://www.splunk.com/en_us/download/splunk-enterprise.html"
echo ""
echo "  □ You can log in to Splunk Web UI"
echo "    - URL: https://<your-splunk-instance>:8000 (Enterprise)"
echo "    - URL: https://<your-instance>.splunkcloud.com (Cloud)"
echo ""
echo "  □ HEC (HTTP Event Collector) is enabled:"
echo "    - Navigate to: Settings > Data Inputs > HTTP Event Collector"
echo "    - Click 'Global Settings'"
echo "    - Ensure 'All Tokens' is set to 'Enabled'"
echo "    - Default port: 8088"
echo ""
echo "  □ A HEC token has been created with:"
echo "    - Name: fsxn-audit-log-shipper"
echo "    - Source type: fsxn:ontap:audit"
echo "    - Index: fsxn_audit"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Check SPLUNK_HEC_ENDPOINT environment variable
# ─────────────────────────────────────────────────────────────────────────────

print_step "2" "Checking SPLUNK_HEC_ENDPOINT environment variable"
echo ""

if [[ -z "${SPLUNK_HEC_ENDPOINT:-}" ]]; then
    print_warn "SPLUNK_HEC_ENDPOINT is not set."
    echo ""
    echo "  To set it, run:"
    echo ""
    echo "    export SPLUNK_HEC_ENDPOINT='https://<your-splunk-host>:8088'"
    echo ""
    echo "  Examples:"
    echo "    export SPLUNK_HEC_ENDPOINT='https://splunk.example.com:8088'"
    echo "    export SPLUNK_HEC_ENDPOINT='https://prd-p-xxxxx.splunkcloud.com:8088'"
    echo ""
    ENDPOINT_SET=false
else
    print_pass "SPLUNK_HEC_ENDPOINT is set: ${SPLUNK_HEC_ENDPOINT}"
    ENDPOINT_SET=true
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Test HEC health endpoint
# ─────────────────────────────────────────────────────────────────────────────

print_step "3" "Testing HEC Health Endpoint"
echo ""

if [[ "${ENDPOINT_SET}" == "true" ]]; then
    HEALTH_URL="${SPLUNK_HEC_ENDPOINT}/services/collector/health"
    print_info "Testing: ${HEALTH_URL}"
    echo ""

    # Attempt to reach the health endpoint
    HTTP_CODE=$(curl -k -s -o /tmp/splunk_health_response.txt -w "%{http_code}" \
        --connect-timeout 10 \
        --max-time 30 \
        "${HEALTH_URL}" 2>/dev/null || echo "000")

    if [[ "${HTTP_CODE}" == "200" ]]; then
        print_pass "HEC health endpoint returned HTTP 200 — HEC is active and reachable!"
        echo ""
        echo "  Response body:"
        echo "  $(cat /tmp/splunk_health_response.txt 2>/dev/null || echo '(empty)')"
        echo ""
        HEALTH_STATUS="PASS"
    elif [[ "${HTTP_CODE}" == "000" ]]; then
        print_fail "Could not connect to HEC endpoint (connection refused or timeout)."
        echo ""
        echo "  Possible causes:"
        echo "    - Splunk instance is not running"
        echo "    - Firewall blocking port 8088"
        echo "    - Incorrect hostname or port"
        echo "    - SSL/TLS certificate issues"
        echo ""
        HEALTH_STATUS="FAIL"
    elif [[ "${HTTP_CODE}" == "503" ]]; then
        print_warn "HEC returned HTTP 503 — HEC is disabled or unhealthy."
        echo ""
        echo "  Resolution:"
        echo "    1. Log in to Splunk Web"
        echo "    2. Go to Settings > Data Inputs > HTTP Event Collector"
        echo "    3. Click 'Global Settings'"
        echo "    4. Set 'All Tokens' to 'Enabled'"
        echo "    5. Save and retry"
        echo ""
        HEALTH_STATUS="FAIL"
    else
        print_warn "HEC returned HTTP ${HTTP_CODE} (unexpected)."
        echo ""
        echo "  Response body:"
        echo "  $(cat /tmp/splunk_health_response.txt 2>/dev/null || echo '(empty)')"
        echo ""
        HEALTH_STATUS="WARN"
    fi

    # Cleanup
    rm -f /tmp/splunk_health_response.txt
else
    print_info "Skipping health check (SPLUNK_HEC_ENDPOINT not set)."
    echo ""
    echo "  Manual verification command:"
    echo ""
    echo "    curl -k https://<SPLUNK_HOST>:8088/services/collector/health"
    echo ""
    echo "  Expected response: HTTP 200 with body:"
    echo '    {"text":"HEC is healthy","code":17}'
    echo ""
    HEALTH_STATUS="SKIP"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Additional verification commands
# ─────────────────────────────────────────────────────────────────────────────

print_step "4" "Additional Verification Commands"
echo ""
echo "  After confirming HEC is healthy, test token authentication:"
echo ""
echo "    curl -k \\"
echo "      -H 'Authorization: Splunk <YOUR_HEC_TOKEN>' \\"
echo "      -d '{\"event\": \"test from verify-splunk-account.sh\", \"sourcetype\": \"manual\"}' \\"
echo "      https://<SPLUNK_HOST>:8088/services/collector/event"
echo ""
echo "  Expected response:"
echo '    {"text":"Success","code":0}'
echo ""
echo "  If you receive HTTP 403, verify:"
echo "    - The HEC token is correct (UUID format: 8-4-4-4-12 hex)"
echo "    - The token is enabled in Splunk"
echo "    - The token has the correct index and sourcetype assigned"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

print_header "Verification Summary"

if [[ "${ENDPOINT_SET}" == "true" ]]; then
    ENV_STATUS="${GREEN}SET${NC}"
else
    ENV_STATUS="${YELLOW}NOT SET${NC}"
fi

case "${HEALTH_STATUS}" in
    PASS) HEALTH_DISPLAY="${GREEN}PASS${NC}" ;;
    FAIL) HEALTH_DISPLAY="${RED}FAIL${NC}" ;;
    WARN) HEALTH_DISPLAY="${YELLOW}WARN${NC}" ;;
    SKIP) HEALTH_DISPLAY="${YELLOW}SKIPPED${NC}" ;;
esac

echo -e "  Environment Variable (SPLUNK_HEC_ENDPOINT): ${ENV_STATUS}"
echo -e "  HEC Health Check:                           ${HEALTH_DISPLAY}"
echo ""

if [[ "${HEALTH_STATUS}" == "PASS" ]]; then
    echo -e "  ${GREEN}✓ Splunk HEC endpoint is reachable and healthy.${NC}"
    echo "    Proceed to task 14.2 (HEC Token creation) if not already done."
    exit 0
elif [[ "${HEALTH_STATUS}" == "SKIP" ]]; then
    echo -e "  ${YELLOW}⚠ Set SPLUNK_HEC_ENDPOINT and re-run this script to verify connectivity.${NC}"
    exit 0
else
    echo -e "  ${RED}✗ HEC endpoint is not reachable or unhealthy.${NC}"
    echo "    Please check the troubleshooting steps above."
    exit 1
fi
