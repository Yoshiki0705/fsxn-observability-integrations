#!/usr/bin/env bash
# register-secret.sh — Register Splunk HEC Token in AWS Secrets Manager
#
# This script stores a Splunk HEC token in AWS Secrets Manager for use
# by the Lambda log shipper. It validates the token format, creates or
# updates the secret, verifies retrieval, and runs the token validator.
#
# Usage:
#   ./register-secret.sh --token <HEC_TOKEN> [--region <REGION>]
#
# Examples:
#   ./register-secret.sh --token "12345678-abcd-ef01-2345-6789abcdef01"
#   ./register-secret.sh --token "12345678-abcd-ef01-2345-6789abcdef01" --region us-east-1
#
# Requirements: AWS CLI v2, Python 3, boto3

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
SECRET_NAME="splunk/fsxn-hec-token"
DEFAULT_REGION="ap-northeast-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
TOKEN_VALIDATOR="${PROJECT_ROOT}/scripts/verification/splunk_token_validator.py"

# UUID pattern: 8-4-4-4-12 hexadecimal characters
UUID_REGEX='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

# =============================================================================
# Helper functions
# =============================================================================
usage() {
    cat <<EOF
Usage: $(basename "$0") --token <HEC_TOKEN> [--region <REGION>]

Register a Splunk HEC token in AWS Secrets Manager.

Options:
  --token   Splunk HEC token (UUID format: 8-4-4-4-12 hex characters) [required]
  --region  AWS region (default: ${DEFAULT_REGION})
  --help    Show this help message

Secret name: ${SECRET_NAME}
EOF
    exit 0
}

log_info() {
    echo "[INFO] $*"
}

log_pass() {
    echo "[PASS] $*"
}

log_fail() {
    echo "[FAIL] $*"
}

log_error() {
    echo "[ERROR] $*" >&2
}

# =============================================================================
# Argument parsing
# =============================================================================
TOKEN=""
REGION="${AWS_REGION:-${DEFAULT_REGION}}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)
            TOKEN="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# =============================================================================
# Validation
# =============================================================================
if [[ -z "${TOKEN}" ]]; then
    log_error "Missing required argument: --token"
    echo ""
    usage
fi

# Step 1: Validate token format (UUID: 8-4-4-4-12 hex)
log_info "Step 1: Validating HEC token format..."
if [[ "${TOKEN}" =~ ${UUID_REGEX} ]]; then
    log_pass "Token format is valid (UUID: 8-4-4-4-12 hex)"
else
    log_fail "Token format is invalid"
    log_error "Expected UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (8-4-4-4-12 hex characters)"
    log_error "Received: ${TOKEN}"
    exit 1
fi

# Step 2: Check if secret already exists
log_info "Step 2: Checking if secret '${SECRET_NAME}' exists in region ${REGION}..."
SECRET_EXISTS=false
SECRET_ARN=""

if aws secretsmanager describe-secret \
    --secret-id "${SECRET_NAME}" \
    --region "${REGION}" \
    --output json 2>/dev/null; then
    SECRET_EXISTS=true
    SECRET_ARN=$(aws secretsmanager describe-secret \
        --secret-id "${SECRET_NAME}" \
        --region "${REGION}" \
        --query 'ARN' \
        --output text)
    log_info "Secret already exists: ${SECRET_ARN}"
fi

# Step 3: Create or update the secret
if [[ "${SECRET_EXISTS}" == "true" ]]; then
    log_info "Step 3: Updating existing secret..."
    aws secretsmanager put-secret-value \
        --secret-id "${SECRET_NAME}" \
        --secret-string "${TOKEN}" \
        --region "${REGION}" \
        --output json > /dev/null
    log_pass "Secret updated successfully"
else
    log_info "Step 3: Creating new secret..."
    CREATE_OUTPUT=$(aws secretsmanager create-secret \
        --name "${SECRET_NAME}" \
        --description "Splunk HEC Token for FSxN audit log integration" \
        --secret-string "${TOKEN}" \
        --region "${REGION}" \
        --output json)
    SECRET_ARN=$(echo "${CREATE_OUTPUT}" | python3 -c "import sys, json; print(json.load(sys.stdin)['ARN'])")
    log_pass "Secret created successfully"
fi

# Step 4: Verify the stored secret is retrievable
log_info "Step 4: Verifying secret is retrievable..."
RETRIEVED_TOKEN=$(aws secretsmanager get-secret-value \
    --secret-id "${SECRET_NAME}" \
    --region "${REGION}" \
    --query 'SecretString' \
    --output text)

if [[ "${RETRIEVED_TOKEN}" == "${TOKEN}" ]]; then
    log_pass "Secret retrieval verified — stored value matches input"
else
    log_fail "Secret retrieval mismatch"
    log_error "Stored value does not match the provided token"
    exit 1
fi

# Step 5: Run the splunk_token_validator.py to confirm format
log_info "Step 5: Running splunk_token_validator.py..."
if [[ -f "${TOKEN_VALIDATOR}" ]]; then
    if python3 "${TOKEN_VALIDATOR}" --secret-arn "${SECRET_ARN}"; then
        log_pass "Token validator confirmed format is correct"
    else
        log_fail "Token validator reported an issue"
        exit 1
    fi
else
    log_info "Token validator not found at ${TOKEN_VALIDATOR} — skipping (local format check passed)"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "============================================================"
echo "  RESULT: PASS — HEC Token registered successfully"
echo "============================================================"
echo ""
echo "  Secret Name : ${SECRET_NAME}"
echo "  Secret ARN  : ${SECRET_ARN}"
echo "  Region      : ${REGION}"
echo ""
echo "  Use this ARN as the CloudFormation parameter:"
echo "    SplunkHecTokenSecretArn=${SECRET_ARN}"
echo ""
echo "  Example deployment command:"
echo "    aws cloudformation deploy \\"
echo "      --template-file integrations/splunk-serverless/template.yaml \\"
echo "      --stack-name fsxn-splunk-integration \\"
echo "      --parameter-overrides \\"
echo "        SplunkHecTokenSecretArn=${SECRET_ARN} \\"
echo "        SplunkHecEndpoint=https://<your-splunk-instance>:8088 \\"
echo "        S3AccessPointArn=<your-s3-ap-arn> \\"
echo "        S3BucketName=<your-bucket-name> \\"
echo "      --capabilities CAPABILITY_IAM \\"
echo "      --region ${REGION}"
echo ""
