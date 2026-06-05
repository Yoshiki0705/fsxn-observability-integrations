#!/bin/bash
# Deploy CrowdStrike Falcon LogScale integration stack.
set -euo pipefail

STACK_NAME="${STACK_PREFIX:-fsxn-crowdstrike}-integration"
REGION="${AWS_REGION:-ap-northeast-1}"
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/template.yaml"

echo "Deploying: ${STACK_NAME} (${REGION})"

if [ -z "${FSX_S3_ACCESS_POINT_ARN:-}" ]; then
  echo "Error: FSX_S3_ACCESS_POINT_ARN is required"
  exit 1
fi

if [ -z "${LOGSCALE_INGEST_TOKEN_SECRET_ARN:-}" ]; then
  echo "Error: LOGSCALE_INGEST_TOKEN_SECRET_ARN is required"
  exit 1
fi

aws cloudformation deploy \
  --template-file "${TEMPLATE}" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --parameter-overrides \
    FsxS3AccessPointArn="${FSX_S3_ACCESS_POINT_ARN}" \
    LogScaleIngestTokenSecretArn="${LOGSCALE_INGEST_TOKEN_SECRET_ARN}" \
    LogScaleUrl="${LOGSCALE_URL:-https://cloud.us.humio.com}" \
    LogLevel="${LOG_LEVEL:-INFO}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo "Done: ${STACK_NAME}"
