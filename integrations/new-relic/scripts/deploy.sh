#!/bin/bash
# Deploy all New Relic integration stacks for FSx for ONTAP.
#
# This script deploys:
#   1. Main audit log stack (template.yaml)
#   2. EMS webhook stack (template-ems.yaml)
#   3. FPolicy stack (template-fpolicy.yaml)
#   4. Updates Lambda function code for all handlers
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate permissions
#   - New Relic License Key stored in Secrets Manager
#   - S3 Access Point created (see docs/en/prerequisites.md)
#
# Usage:
#   export NR_SECRET_ARN="arn:aws:secretsmanager:..."
#   export S3_ACCESS_POINT_ARN="arn:aws:s3:..."
#   export S3_BUCKET_NAME="your-fsxn-audit-log-bucket"
#   bash integrations/new-relic/scripts/deploy.sh
#
# Options:
#   --audit-only    Deploy only the audit log poller (template.yaml)
#   --all           Deploy all stacks (default)

set -euo pipefail

DEPLOY_MODE="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --audit-only) DEPLOY_MODE="audit-only"; shift ;;
    --all)        DEPLOY_MODE="all"; shift ;;
    -h|--help)
      echo "Usage: bash deploy.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --audit-only    Deploy only the audit log poller"
      echo "  --all           Deploy all stacks: audit + EMS + FPolicy (default)"
      echo ""
      echo "Environment variables (required):"
      echo "  NR_SECRET_ARN         Secrets Manager ARN for New Relic License Key"
      echo "  S3_ACCESS_POINT_ARN   FSx for ONTAP S3 Access Point ARN"
      echo "  S3_BUCKET_NAME        S3 bucket name for audit logs"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
STACK_PREFIX="${STACK_PREFIX:-fsxn-new-relic}"

NR_SECRET_ARN="${NR_SECRET_ARN:-}"
S3_ACCESS_POINT_ARN="${S3_ACCESS_POINT_ARN:-}"
S3_BUCKET_NAME="${S3_BUCKET_NAME:-}"
NR_REGION="${NR_REGION:-US}"
NR_ENDPOINT="${NR_ENDPOINT:-https://log-api.newrelic.com/log/v1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
LAMBDA_MEMORY="${LAMBDA_MEMORY:-256}"
LAMBDA_TIMEOUT="${LAMBDA_TIMEOUT:-300}"
FPOLICY_EVENT_BUS="${FPOLICY_EVENT_BUS:-fsxn-fpolicy-events}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTEGRATION_DIR="$(dirname "$SCRIPT_DIR")"

validate_required() {
  local var_name="$1"
  local var_value="${!var_name:-}"
  if [ -z "$var_value" ]; then
    echo "ERROR: $var_name is required but not set."
    return 1
  fi
}

echo "=== FSx for ONTAP New Relic Integration Deployment ==="
echo "Region: ${AWS_REGION} | Stack prefix: ${STACK_PREFIX} | NR Region: ${NR_REGION}"

ERRORS=0
validate_required "NR_SECRET_ARN" || ERRORS=$((ERRORS + 1))
validate_required "S3_ACCESS_POINT_ARN" || ERRORS=$((ERRORS + 1))
validate_required "S3_BUCKET_NAME" || ERRORS=$((ERRORS + 1))

if [ "$ERRORS" -gt 0 ]; then
  echo "Set the required environment variables and re-run."
  exit 1
fi

# --- Step 1: Main audit log stack ---
echo "--- Step 1: Deploying main audit log stack ---"
aws cloudformation deploy \
  --template-file "${INTEGRATION_DIR}/template.yaml" \
  --stack-name "${STACK_PREFIX}-integration" \
  --capabilities CAPABILITY_IAM \
  --region "${AWS_REGION}" \
  --parameter-overrides \
    S3AccessPointArn="${S3_ACCESS_POINT_ARN}" \
    NewRelicLicenseKeySecretArn="${NR_SECRET_ARN}" \
    NewRelicRegion="${NR_REGION}" \
    S3BucketName="${S3_BUCKET_NAME}" \
    LogLevel="${LOG_LEVEL}" \
    LambdaMemorySize="${LAMBDA_MEMORY}" \
    LambdaTimeout="${LAMBDA_TIMEOUT}" \
  --no-fail-on-empty-changeset
echo "  ✅ Main stack: ${STACK_PREFIX}-integration"

if [ "$DEPLOY_MODE" = "all" ]; then

# --- Step 2: EMS stack ---
echo "--- Step 2: Deploying EMS webhook stack ---"
aws cloudformation deploy \
  --template-file "${INTEGRATION_DIR}/template-ems.yaml" \
  --stack-name "${STACK_PREFIX}-ems" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${AWS_REGION}" \
  --parameter-overrides \
    NewRelicLicenseKeySecretArn="${NR_SECRET_ARN}" \
    NewRelicEndpoint="${NR_ENDPOINT}" \
    LogLevel="${LOG_LEVEL}" \
  --no-fail-on-empty-changeset
echo "  ✅ EMS stack: ${STACK_PREFIX}-ems"

# --- Step 3: FPolicy stack ---
echo "--- Step 3: Deploying FPolicy stack ---"
aws cloudformation deploy \
  --template-file "${INTEGRATION_DIR}/template-fpolicy.yaml" \
  --stack-name "${STACK_PREFIX}-fpolicy" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${AWS_REGION}" \
  --parameter-overrides \
    NewRelicLicenseKeySecretArn="${NR_SECRET_ARN}" \
    NewRelicEndpoint="${NR_ENDPOINT}" \
    EventBusName="${FPOLICY_EVENT_BUS}" \
    LogLevel="${LOG_LEVEL}" \
  --no-fail-on-empty-changeset
echo "  ✅ FPolicy stack: ${STACK_PREFIX}-fpolicy"

fi

# --- Step 4: Update Lambda code ---
echo "--- Step 4: Updating Lambda function code ---"
cd "${INTEGRATION_DIR}/lambda"

zip -q /tmp/nr-handler.zip handler.py
aws lambda update-function-code \
  --function-name "${STACK_PREFIX}-integration-shipper" \
  --zip-file fileb:///tmp/nr-handler.zip \
  --region "${AWS_REGION}" > /dev/null
rm -f /tmp/nr-handler.zip
echo "  ✅ Main handler updated"

if [ "$DEPLOY_MODE" = "all" ]; then
  zip -q /tmp/nr-ems-handler.zip ems_handler.py
  aws lambda update-function-code \
    --function-name "${STACK_PREFIX}-ems-ems-handler" \
    --zip-file fileb:///tmp/nr-ems-handler.zip \
    --region "${AWS_REGION}" > /dev/null
  rm -f /tmp/nr-ems-handler.zip
  echo "  ✅ EMS handler updated"

  zip -q /tmp/nr-fpolicy-handler.zip fpolicy_handler.py
  aws lambda update-function-code \
    --function-name "${STACK_PREFIX}-fpolicy-handler" \
    --zip-file fileb:///tmp/nr-fpolicy-handler.zip \
    --region "${AWS_REGION}" > /dev/null
  rm -f /tmp/nr-fpolicy-handler.zip
  echo "  ✅ FPolicy handler updated"
fi

echo ""
echo "=== Done ==="
echo "Verify: SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 15 minutes ago"
