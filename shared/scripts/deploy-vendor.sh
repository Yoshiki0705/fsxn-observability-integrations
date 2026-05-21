#!/bin/bash
# ============================================================================
# Shared vendor integration deployment script for FSx for ONTAP Observability.
#
# This is a GENERIC deployment script that works for any vendor integration.
# Each vendor's deploy.sh should call this script with vendor-specific
# environment variables.
#
# ============================================================================
# DEPLOYMENT ORDER
# ============================================================================
#
#   1. Main integration stack (S3 audit log -> vendor API)
#   2. EMS Lambda stack (EMS webhook -> vendor API)
#   3. FPolicy Lambda stack (FPolicy EventBridge -> vendor API)
#   4. Update Lambda function code (deploy actual handlers)
#
# ============================================================================
# ENVIRONMENT VARIABLES (REQUIRED)
# ============================================================================
#
#   STACK_PREFIX         CloudFormation stack name prefix (e.g., fsxn-grafana)
#   VENDOR_SECRET_ARN    Secrets Manager ARN with vendor credentials
#   VENDOR_ENDPOINT      Vendor API endpoint URL
#   S3_ACCESS_POINT_ARN  S3 Access Point ARN for audit logs
#   S3_BUCKET_NAME       S3 bucket name
#   INTEGRATION_DIR      Path to vendor integration directory
#
# ============================================================================
# ENVIRONMENT VARIABLES (OPTIONAL)
# ============================================================================
#
#   AWS_REGION           AWS region (default: ap-northeast-1)
#   S3_KEY_PREFIX        S3 key prefix filter
#   LOG_LEVEL            Lambda log level (default: INFO)
#   LAMBDA_MEMORY        Lambda memory in MB (default: 256)
#   LAMBDA_TIMEOUT       Lambda timeout in seconds (default: 300)
#   EMS_PARSER_LAYER_ARN EMS Parser Lambda Layer ARN
#   FPOLICY_EVENT_BUS    EventBridge bus name (default: fsxn-fpolicy-events)
#   SKIP_CODE_DEPLOY     Set to "true" to skip Lambda code update
#   VENDOR_NAME          Human-readable name for display
#
# ============================================================================

set -euo pipefail

# --- Configuration ----------------------------------------------------------

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
STACK_PREFIX="${STACK_PREFIX:-}"
VENDOR_SECRET_ARN="${VENDOR_SECRET_ARN:-}"
VENDOR_ENDPOINT="${VENDOR_ENDPOINT:-}"
S3_ACCESS_POINT_ARN="${S3_ACCESS_POINT_ARN:-}"
S3_BUCKET_NAME="${S3_BUCKET_NAME:-}"
INTEGRATION_DIR="${INTEGRATION_DIR:-}"
VENDOR_NAME="${VENDOR_NAME:-}"

S3_KEY_PREFIX="${S3_KEY_PREFIX:-}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
LAMBDA_MEMORY="${LAMBDA_MEMORY:-256}"
LAMBDA_TIMEOUT="${LAMBDA_TIMEOUT:-300}"
EMS_PARSER_LAYER_ARN="${EMS_PARSER_LAYER_ARN:-}"
FPOLICY_EVENT_BUS="${FPOLICY_EVENT_BUS:-fsxn-fpolicy-events}"
SKIP_CODE_DEPLOY="${SKIP_CODE_DEPLOY:-false}"

# --- Parse arguments --------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-code) SKIP_CODE_DEPLOY=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--skip-code]"
      echo ""
      echo "Required environment variables:"
      echo "  STACK_PREFIX, VENDOR_SECRET_ARN, VENDOR_ENDPOINT,"
      echo "  S3_ACCESS_POINT_ARN, S3_BUCKET_NAME, INTEGRATION_DIR"
      echo ""
      echo "Options:"
      echo "  --skip-code    Skip Lambda function code deployment"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# --- Validation -------------------------------------------------------------

validate_required() {
  local var_name="$1"
  local var_value="${!var_name:-}"
  if [ -z "$var_value" ]; then
    echo "ERROR: $var_name is required but not set."
    return 1
  fi
}

ERRORS=0
validate_required "STACK_PREFIX" || ERRORS=$((ERRORS + 1))
validate_required "VENDOR_SECRET_ARN" || ERRORS=$((ERRORS + 1))
validate_required "VENDOR_ENDPOINT" || ERRORS=$((ERRORS + 1))
validate_required "S3_ACCESS_POINT_ARN" || ERRORS=$((ERRORS + 1))
validate_required "S3_BUCKET_NAME" || ERRORS=$((ERRORS + 1))
validate_required "INTEGRATION_DIR" || ERRORS=$((ERRORS + 1))

if [ "$ERRORS" -gt 0 ]; then
  echo "Set the required environment variables and re-run."
  exit 1
fi

if [ -z "$VENDOR_NAME" ]; then
  VENDOR_NAME="${STACK_PREFIX#fsxn-}"
fi

echo "=== FSxN ${VENDOR_NAME} Integration Deployment ==="
echo "Region: ${AWS_REGION}"
echo "Stack prefix: ${STACK_PREFIX}"
echo "Endpoint: ${VENDOR_ENDPOINT}"
echo ""

# --- Step 1: Main integration stack ----------------------------------------

MAIN_TEMPLATE="${INTEGRATION_DIR}/template.yaml"
if [ -f "$MAIN_TEMPLATE" ]; then
  echo "--- Step 1/4: Main integration stack ---"
  aws cloudformation deploy \
    --template-file "$MAIN_TEMPLATE" \
    --stack-name "${STACK_PREFIX}-integration" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset
  echo "  ✅ ${STACK_PREFIX}-integration deployed"
else
  echo "  ⏭️  No template.yaml, skipping."
fi

# --- Step 2: EMS stack ------------------------------------------------------

EMS_TEMPLATE="${INTEGRATION_DIR}/template-ems.yaml"
if [ -f "$EMS_TEMPLATE" ]; then
  echo "--- Step 2/4: EMS Lambda stack ---"
  aws cloudformation deploy \
    --template-file "$EMS_TEMPLATE" \
    --stack-name "${STACK_PREFIX}-ems" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset
  echo "  ✅ ${STACK_PREFIX}-ems deployed"
else
  echo "  ⏭️  No template-ems.yaml, skipping."
fi

# --- Step 3: FPolicy stack --------------------------------------------------

FPOLICY_TEMPLATE="${INTEGRATION_DIR}/template-fpolicy.yaml"
if [ -f "$FPOLICY_TEMPLATE" ]; then
  echo "--- Step 3/4: FPolicy Lambda stack ---"
  aws cloudformation deploy \
    --template-file "$FPOLICY_TEMPLATE" \
    --stack-name "${STACK_PREFIX}-fpolicy" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset
  echo "  ✅ ${STACK_PREFIX}-fpolicy deployed"
else
  echo "  ⏭️  No template-fpolicy.yaml, skipping."
fi

# --- Step 4: Update Lambda code ---------------------------------------------

if [ "$SKIP_CODE_DEPLOY" = true ]; then
  echo "--- Step 4/4: Skipped (--skip-code) ---"
else
  echo "--- Step 4/4: Updating Lambda function code ---"
  LAMBDA_DIR="${INTEGRATION_DIR}/lambda"

  if [ -f "${LAMBDA_DIR}/handler.py" ]; then
    zip -qj /tmp/_deploy_handler.zip "${LAMBDA_DIR}/handler.py"
    aws lambda update-function-code \
      --function-name "${STACK_PREFIX}-integration-shipper" \
      --zip-file fileb:///tmp/_deploy_handler.zip \
      --region "${AWS_REGION}" > /dev/null 2>&1 && echo "  ✅ Main handler" || echo "  ⏭️  Main handler (not found)"
    rm -f /tmp/_deploy_handler.zip
  fi

  if [ -f "${LAMBDA_DIR}/ems_handler.py" ]; then
    zip -qj /tmp/_deploy_ems.zip "${LAMBDA_DIR}/ems_handler.py"
    aws lambda update-function-code \
      --function-name "${STACK_PREFIX}-ems-ems-handler" \
      --zip-file fileb:///tmp/_deploy_ems.zip \
      --region "${AWS_REGION}" > /dev/null 2>&1 && echo "  ✅ EMS handler" || echo "  ⏭️  EMS handler (not found)"
    rm -f /tmp/_deploy_ems.zip
  fi

  if [ -f "${LAMBDA_DIR}/fpolicy_handler.py" ]; then
    zip -qj /tmp/_deploy_fpolicy.zip "${LAMBDA_DIR}/fpolicy_handler.py"
    aws lambda update-function-code \
      --function-name "${STACK_PREFIX}-fpolicy-handler" \
      --zip-file fileb:///tmp/_deploy_fpolicy.zip \
      --region "${AWS_REGION}" > /dev/null 2>&1 && echo "  ✅ FPolicy handler" || echo "  ⏭️  FPolicy handler (not found)"
    rm -f /tmp/_deploy_fpolicy.zip
  fi
fi

# --- Summary ----------------------------------------------------------------

echo ""
echo "=== ${VENDOR_NAME} Deployment Complete ==="
echo ""
echo "Cleanup: bash integrations/<vendor>/scripts/cleanup.sh"
