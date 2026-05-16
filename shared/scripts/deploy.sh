#!/bin/bash
set -euo pipefail

# FSxN Observability Integration - Deployment Script
# Usage: ./deploy.sh <vendor> <stack-name> [--region <region>]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default values
REGION="${AWS_DEFAULT_REGION:-ap-northeast-1}"
VENDOR=""
STACK_NAME=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --region)
      REGION="$2"
      shift 2
      ;;
    *)
      if [[ -z "$VENDOR" ]]; then
        VENDOR="$1"
      elif [[ -z "$STACK_NAME" ]]; then
        STACK_NAME="$1"
      fi
      shift
      ;;
  esac
done

if [[ -z "$VENDOR" || -z "$STACK_NAME" ]]; then
  echo "Usage: $0 <vendor> <stack-name> [--region <region>]"
  echo "  Vendors: datadog, new-relic, grafana, splunk-serverless, elastic, dynatrace, sumo-logic, honeycomb, otel-collector"
  exit 1
fi

TEMPLATE_PATH="${PROJECT_ROOT}/integrations/${VENDOR}/template.yaml"

if [[ ! -f "$TEMPLATE_PATH" ]]; then
  echo "Error: Template not found at ${TEMPLATE_PATH}"
  exit 1
fi

echo "🚀 Deploying ${VENDOR} integration..."
echo "   Stack: ${STACK_NAME}"
echo "   Region: ${REGION}"
echo "   Template: ${TEMPLATE_PATH}"
echo ""

# Validate template
echo "📋 Validating template..."
aws cloudformation validate-template \
  --template-body "file://${TEMPLATE_PATH}" \
  --region "${REGION}" > /dev/null

echo "✅ Template valid"
echo ""

# Deploy
echo "📦 Deploying stack..."
aws cloudformation deploy \
  --template-file "${TEMPLATE_PATH}" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo ""
echo "✅ Deployment complete: ${STACK_NAME}"
