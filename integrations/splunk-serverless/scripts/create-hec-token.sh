#!/usr/bin/env bash
# =============================================================================
# create-hec-token.sh — Splunk HEC Token Creation Helper & Verification Script
#
# This script documents the manual steps to create a HEC token in Splunk UI
# and provides automated verification of an existing token.
#
# Usage:
#   ./create-hec-token.sh                          # Show manual steps
#   ./create-hec-token.sh --endpoint URL --token TOKEN  # Verify token
#
# Requirements: 1.1
# =============================================================================
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# UUID pattern: 8-4-4-4-12 hexadecimal characters
UUID_PATTERN='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

# Default values
ENDPOINT=""
TOKEN=""

# =============================================================================
# Functions
# =============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}=============================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}=============================================================================${NC}"
    echo ""
}

print_pass() {
    echo -e "  ${GREEN}[PASS]${NC} $1"
}

print_fail() {
    echo -e "  ${RED}[FAIL]${NC} $1"
}

print_info() {
    echo -e "  ${YELLOW}[INFO]${NC} $1"
}

show_manual_steps() {
    print_header "Splunk HEC Token — Manual Creation Steps"

    echo "Follow these steps to create a HEC token in Splunk UI:"
    echo ""
    echo "  1. Log in to Splunk Web"
    echo "  2. Navigate to: Settings > Data Inputs > HTTP Event Collector"
    echo "  3. Ensure HEC is enabled in Global Settings"
    echo "  4. Click 'New Token'"
    echo "  5. Configure the token:"
    echo ""
    echo "     Name:        fsxn-audit-log-shipper"
    echo "     Source type: fsxn:ontap:audit"
    echo "     Index:       fsxn_audit"
    echo ""
    echo "  6. Copy the generated HEC Token (UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
    echo ""
    echo -e "  ${YELLOW}Token format example:${NC} 12345678-abcd-ef01-2345-6789abcdef01"
    echo ""
    echo "  7. Store the token in AWS Secrets Manager:"
    echo ""
    echo "     aws secretsmanager create-secret \\"
    echo "       --name \"splunk/fsxn-hec-token\" \\"
    echo "       --description \"Splunk HEC Token for FSxN audit log integration\" \\"
    echo "       --secret-string \"<YOUR_HEC_TOKEN>\" \\"
    echo "       --region ap-northeast-1"
    echo ""
    echo "─────────────────────────────────────────────────────────────────────────────"
    echo ""
    echo "To verify an existing token, run:"
    echo ""
    echo "  $0 --endpoint https://<SPLUNK_HOST>:8088 --token <HEC_TOKEN>"
    echo ""
}

validate_token_format() {
    local token="$1"

    # Convert to lowercase for validation
    local lower_token
    lower_token=$(echo "$token" | tr '[:upper:]' '[:lower:]')

    if echo "$lower_token" | grep -qE "$UUID_PATTERN"; then
        return 0
    else
        return 1
    fi
}

verify_hec_endpoint() {
    local endpoint="$1"
    local token="$2"
    local results=0

    print_header "Splunk HEC Token Verification"

    # Step 1: Validate token format
    echo "Step 1: Token Format Validation"
    echo "─────────────────────────────────────────────────────────────────────────────"
    if validate_token_format "$token"; then
        print_pass "Token matches UUID format (8-4-4-4-12 hex)"
    else
        print_fail "Token does NOT match UUID format (8-4-4-4-12 hex)"
        print_info "Expected format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        print_info "Received: $token"
        results=1
    fi
    echo ""

    # Step 2: Check HEC health endpoint
    echo "Step 2: HEC Endpoint Health Check"
    echo "─────────────────────────────────────────────────────────────────────────────"
    local health_url="${endpoint}/services/collector/health"
    print_info "Checking: $health_url"

    local health_status
    health_status=$(curl -k -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 10 \
        --max-time 15 \
        "$health_url" 2>/dev/null) || health_status="000"

    if [ "$health_status" = "200" ]; then
        print_pass "HEC health endpoint returned HTTP 200"
    elif [ "$health_status" = "000" ]; then
        print_fail "Cannot connect to HEC endpoint (connection timeout or DNS failure)"
        print_info "Verify the endpoint URL and network connectivity"
        results=1
    else
        print_fail "HEC health endpoint returned HTTP $health_status (expected 200)"
        results=1
    fi
    echo ""

    # Step 3: Send test event
    echo "Step 3: Send Test Event to HEC"
    echo "─────────────────────────────────────────────────────────────────────────────"
    local event_url="${endpoint}/services/collector/event"
    local test_payload='{"event":"HEC token verification test","sourcetype":"fsxn:ontap:audit","index":"fsxn_audit","source":"create-hec-token.sh"}'

    print_info "Sending test event to: $event_url"

    local response
    local http_code
    response=$(curl -k -s -w "\n%{http_code}" \
        --connect-timeout 10 \
        --max-time 15 \
        -H "Authorization: Splunk ${token}" \
        -d "$test_payload" \
        "$event_url" 2>/dev/null) || response=$'\n000'

    # Extract HTTP code (last line) and body (everything else)
    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "200" ]; then
        print_pass "Test event accepted (HTTP 200)"
        print_info "Response: $body"
    elif [ "$http_code" = "403" ]; then
        print_fail "Token rejected (HTTP 403 — Invalid or disabled token)"
        print_info "Response: $body"
        print_info "Verify the token is enabled in Splunk HEC settings"
        results=1
    elif [ "$http_code" = "400" ]; then
        print_fail "Bad request (HTTP 400 — Check index/sourcetype configuration)"
        print_info "Response: $body"
        results=1
    elif [ "$http_code" = "000" ]; then
        print_fail "Cannot connect to HEC event endpoint"
        results=1
    else
        print_fail "Unexpected response (HTTP $http_code)"
        print_info "Response: $body"
        results=1
    fi
    echo ""

    # Summary
    echo "─────────────────────────────────────────────────────────────────────────────"
    if [ "$results" -eq 0 ]; then
        echo -e "  ${GREEN}[OVERALL: PASS]${NC} HEC token is valid and endpoint is reachable"
    else
        echo -e "  ${RED}[OVERALL: FAIL]${NC} One or more verification steps failed"
    fi
    echo ""

    return $results
}

usage() {
    echo "Usage: $0 [--endpoint <URL>] [--token <TOKEN>]"
    echo ""
    echo "Options:"
    echo "  --endpoint URL    Splunk HEC endpoint (e.g., https://splunk.example.com:8088)"
    echo "  --token TOKEN     Splunk HEC token (UUID format)"
    echo "  --help            Show this help message"
    echo ""
    echo "If no arguments are provided, displays manual HEC token creation steps."
    echo "If both --endpoint and --token are provided, verifies the token works."
}

# =============================================================================
# Main
# =============================================================================

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --endpoint)
            ENDPOINT="$2"
            shift 2
            ;;
        --token)
            TOKEN="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Decide what to do
if [ -n "$ENDPOINT" ] && [ -n "$TOKEN" ]; then
    # Both provided — run verification
    verify_hec_endpoint "$ENDPOINT" "$TOKEN"
elif [ -n "$ENDPOINT" ] || [ -n "$TOKEN" ]; then
    # Only one provided — error
    echo -e "${RED}Error:${NC} Both --endpoint and --token are required for verification."
    echo ""
    usage
    exit 1
else
    # Neither provided — show manual steps
    show_manual_steps
fi
