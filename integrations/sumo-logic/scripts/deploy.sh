#!/bin/bash
# Deploy Sumo Logic integration stacks for FSx for ONTAP.
set -euo pipefail

DEPLOY_MODE="all"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --audit-only) DEPLOY_MODE="audit-only"; shift ;;
    --all) DEPLOY_MODE="all"; shift ;;
    -h|--help)
      echo "Usage: bash deploy.sh [--audit-only|--all]"
      echo ""
      echo "Required env vars:"
      echo "  SUMO_SECRET_ARN    Secrets Manager ARN"
      echo "  S3_ACCESS_POINT_ARN   FSx for ONTAP S3 Access Point ARN"
      echo "  S3_BUCKET_NAME        S3 bucket name"
      echo "  SOURCE_CATEGORY        Sumo Logic source category (default: aws/fsxn/audit)"
      exit 0 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
STACK_PREFIX="${STACK_PREFIX:-fsxn-sumo-logic}"
SUMO_SECRET_ARN="${SUMO_SECRET_ARN:-}"
S3_ACCESS_POINT_ARN="${S3_ACCESS_POINT_ARN:-}"
S3_BUCKET_NAME="${S3_BUCKET_NAME:-}"
SOURCE_CATEGORY="${SOURCE_CATEGORY:-aws/fsxn/audit}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
FPOLICY_EVENT_BUS="${FPOLICY_EVENT_BUS:-fsxn-fpolicy-events}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTEGRATION_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== FSx for ONTAP Sumo Logic Deployment ==="
for var in SUMO_SECRET_ARN S3_ACCESS_POINT_ARN S3_BUCKET_NAME; do
  if [ -z "${!var:-}" ]; then echo "ERROR: $var not set"; exit 1; fi
done

echo "--- Deploying main audit log stack ---"
aws cloudformation deploy \
  --template-file "${INTEGRATION_DIR}/template.yaml" \
  --stack-name "${STACK_PREFIX}-integration" \
  --capabilities CAPABILITY_IAM --region "${AWS_REGION}" \
  --parameter-overrides \
    S3AccessPointArn="${S3_ACCESS_POINT_ARN}" \
    SumoLogicHttpSourceSecretArn="${SUMO_SECRET_ARN}" \
    S3BucketName="${S3_BUCKET_NAME}" \
    SourceCategory="${SOURCE_CATEGORY}" \
    LogLevel="${LOG_LEVEL}" \
  --no-fail-on-empty-changeset
echo "  ✅ Main stack: ${STACK_PREFIX}-integration"

if [ "$DEPLOY_MODE" = "all" ]; then
  echo "--- Deploying EMS stack ---"
  aws cloudformation deploy \
    --template-file "${INTEGRATION_DIR}/template-ems.yaml" \
    --stack-name "${STACK_PREFIX}-ems" \
    --capabilities CAPABILITY_NAMED_IAM --region "${AWS_REGION}" \
    --parameter-overrides \
      SumoLogicHttpSourceSecretArn="${SUMO_SECRET_ARN}" \
      SourceCategory="${SOURCE_CATEGORY}" LogLevel="${LOG_LEVEL}" \
    --no-fail-on-empty-changeset
  echo "  ✅ EMS stack: ${STACK_PREFIX}-ems"

  echo "--- Deploying FPolicy stack ---"
  aws cloudformation deploy \
    --template-file "${INTEGRATION_DIR}/template-fpolicy.yaml" \
    --stack-name "${STACK_PREFIX}-fpolicy" \
    --capabilities CAPABILITY_NAMED_IAM --region "${AWS_REGION}" \
    --parameter-overrides \
      SumoLogicHttpSourceSecretArn="${SUMO_SECRET_ARN}" \
      SourceCategory="${SOURCE_CATEGORY}" EventBusName="${FPOLICY_EVENT_BUS}" LogLevel="${LOG_LEVEL}" \
    --no-fail-on-empty-changeset
  echo "  ✅ FPolicy stack: ${STACK_PREFIX}-fpolicy"
fi

echo "--- Updating Lambda code ---"
cd "${INTEGRATION_DIR}/lambda"
zip -q /tmp/sumo-logic-handler.zip handler.py
aws lambda update-function-code --function-name "${STACK_PREFIX}-integration-shipper" \
  --zip-file fileb:///tmp/sumo-logic-handler.zip --region "${AWS_REGION}" > /dev/null
rm -f /tmp/sumo-logic-handler.zip
echo "  ✅ Handler updated"
echo ""
echo "=== Done === Check Sumo Logic: _sourceCategory=aws/fsxn/audit"
