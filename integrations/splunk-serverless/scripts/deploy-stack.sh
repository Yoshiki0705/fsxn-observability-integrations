#!/usr/bin/env bash
# deploy-stack.sh — Deploy the Splunk Serverless Integration CloudFormation stack
#
# This script deploys integrations/splunk-serverless/template.yaml, waits for
# completion, validates the stack status, and prints stack outputs.
#
# Usage:
#   ./deploy-stack.sh --hec-endpoint <URL> --secret-arn <ARN> --s3-ap-arn <ARN> --bucket-name <NAME> --ems-api-key-arn <ARN> [OPTIONS]
#
# Examples:
#   ./deploy-stack.sh \
#     --hec-endpoint https://splunk.example.com:8088 \
#     --secret-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk/fsxn-hec-token-XXXXXX \
#     --s3-ap-arn arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
#     --bucket-name my-audit-log-bucket \
#     --ems-api-key-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-api-key-XXXXXX
#
# Requirements: AWS CLI v2

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
DEFAULT_REGION="ap-northeast-1"
DEFAULT_STACK_NAME="fsxn-splunk-integration"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
TEMPLATE_FILE="${PROJECT_ROOT}/integrations/splunk-serverless/template.yaml"

# =============================================================================
# Helper functions
# =============================================================================
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy the Splunk Serverless Integration CloudFormation stack.

Required Options:
  --hec-endpoint    Splunk HEC endpoint URL (e.g., https://splunk.example.com:8088)
  --secret-arn      ARN of the Secrets Manager secret containing the HEC token
  --s3-ap-arn       ARN of the S3 Access Point for FSx ONTAP audit logs
  --bucket-name     S3 bucket name for event notification
  --ems-api-key-arn ARN of the Secrets Manager secret containing the EMS webhook API key

Optional:
  --region          AWS region (default: ${DEFAULT_REGION})
  --stack-name      CloudFormation stack name (default: ${DEFAULT_STACK_NAME})
  --help            Show this help message

Template: integrations/splunk-serverless/template.yaml
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
HEC_ENDPOINT=""
SECRET_ARN=""
S3_AP_ARN=""
BUCKET_NAME=""
EMS_API_KEY_ARN=""
REGION="${AWS_REGION:-${DEFAULT_REGION}}"
STACK_NAME="${DEFAULT_STACK_NAME}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hec-endpoint)
            HEC_ENDPOINT="$2"
            shift 2
            ;;
        --secret-arn)
            SECRET_ARN="$2"
            shift 2
            ;;
        --s3-ap-arn)
            S3_AP_ARN="$2"
            shift 2
            ;;
        --bucket-name)
            BUCKET_NAME="$2"
            shift 2
            ;;
        --ems-api-key-arn)
            EMS_API_KEY_ARN="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --stack-name)
            STACK_NAME="$2"
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
# Validate required parameters
# =============================================================================
MISSING_PARAMS=()

if [[ -z "${HEC_ENDPOINT}" ]]; then
    MISSING_PARAMS+=("--hec-endpoint")
fi
if [[ -z "${SECRET_ARN}" ]]; then
    MISSING_PARAMS+=("--secret-arn")
fi
if [[ -z "${S3_AP_ARN}" ]]; then
    MISSING_PARAMS+=("--s3-ap-arn")
fi
if [[ -z "${BUCKET_NAME}" ]]; then
    MISSING_PARAMS+=("--bucket-name")
fi
if [[ -z "${EMS_API_KEY_ARN}" ]]; then
    MISSING_PARAMS+=("--ems-api-key-arn")
fi

if [[ ${#MISSING_PARAMS[@]} -gt 0 ]]; then
    log_error "Missing required parameters: ${MISSING_PARAMS[*]}"
    echo ""
    usage
fi

# =============================================================================
# Validate template file exists
# =============================================================================
if [[ ! -f "${TEMPLATE_FILE}" ]]; then
    log_fail "Template file not found: ${TEMPLATE_FILE}"
    exit 1
fi

# =============================================================================
# Step 1: Run cfn-lint (if available)
# =============================================================================
log_info "Step 1: Validating CloudFormation template..."
if command -v cfn-lint &>/dev/null; then
    if cfn-lint "${TEMPLATE_FILE}"; then
        log_pass "cfn-lint validation passed"
    else
        log_fail "cfn-lint validation failed"
        log_error "Fix template errors before deploying"
        exit 1
    fi
else
    log_info "cfn-lint not installed — skipping template validation"
    log_info "Install with: pip install cfn-lint"
fi

# =============================================================================
# Step 2: Deploy CloudFormation stack
# =============================================================================
log_info "Step 2: Deploying CloudFormation stack..."
log_info "  Stack name : ${STACK_NAME}"
log_info "  Region     : ${REGION}"
log_info "  Template   : ${TEMPLATE_FILE}"
echo ""

aws cloudformation deploy \
    --template-file "${TEMPLATE_FILE}" \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides \
        S3AccessPointArn="${S3_AP_ARN}" \
        SplunkHecTokenSecretArn="${SECRET_ARN}" \
        SplunkHecEndpoint="${HEC_ENDPOINT}" \
        S3BucketName="${BUCKET_NAME}" \
        EmsApiKeySecretArn="${EMS_API_KEY_ARN}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}" \
    --no-fail-on-empty-changeset

log_info "Deployment command completed"

# =============================================================================
# Step 3: Wait for stack creation/update to complete
# =============================================================================
log_info "Step 3: Checking stack status..."

STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "UNKNOWN")

log_info "Stack status: ${STACK_STATUS}"

# =============================================================================
# Step 4: Validate stack status
# =============================================================================
log_info "Step 4: Validating stack status..."

if [[ "${STACK_STATUS}" == "CREATE_COMPLETE" || "${STACK_STATUS}" == "UPDATE_COMPLETE" ]]; then
    log_pass "Stack is in a successful state: ${STACK_STATUS}"
else
    log_fail "Stack is NOT in a successful state: ${STACK_STATUS}"
    echo ""
    log_info "Checking stack events for failure details..."
    aws cloudformation describe-stack-events \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --query 'StackEvents[?ResourceStatus==`CREATE_FAILED` || ResourceStatus==`UPDATE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
        --output table 2>/dev/null || true
    echo ""
    echo "============================================================"
    echo "  RESULT: FAIL — Stack deployment unsuccessful"
    echo "============================================================"
    echo ""
    echo "  Stack Name   : ${STACK_NAME}"
    echo "  Stack Status : ${STACK_STATUS}"
    echo "  Region       : ${REGION}"
    echo ""
    exit 1
fi

# =============================================================================
# Step 5: Print stack outputs
# =============================================================================
log_info "Step 5: Retrieving stack outputs..."
echo ""

LAMBDA_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionArn`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

EMS_API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`EmsApiEndpoint`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

DLQ_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`DeadLetterQueueArn`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

EMS_DLQ_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`EmsDeadLetterQueueArn`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "============================================================"
echo "  RESULT: PASS — Stack deployed successfully"
echo "============================================================"
echo ""
echo "  Stack Name       : ${STACK_NAME}"
echo "  Stack Status     : ${STACK_STATUS}"
echo "  Region           : ${REGION}"
echo ""
echo "  --- Stack Outputs ---"
echo "  Lambda ARN       : ${LAMBDA_ARN}"
echo "  EMS API Endpoint : ${EMS_API_ENDPOINT}"
echo "  DLQ ARN          : ${DLQ_ARN}"
echo "  EMS DLQ ARN      : ${EMS_DLQ_ARN}"
echo ""
echo "  --- Next Steps ---"
echo "  1. Test Lambda invocation:"
echo "     aws lambda invoke \\"
echo "       --function-name ${STACK_NAME}-shipper \\"
echo "       --payload file://integrations/splunk-serverless/tests/test_data/sample_s3_event.json \\"
echo "       --cli-binary-format raw-in-base64-out \\"
echo "       --region ${REGION} \\"
echo "       response.json"
echo ""
echo "  2. Test EMS webhook:"
echo "     curl -X POST ${EMS_API_ENDPOINT} \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -H 'x-api-key: <YOUR_API_KEY>' \\"
echo "       -d @integrations/splunk-serverless/tests/test_data/sample_ems_event.json"
echo ""
