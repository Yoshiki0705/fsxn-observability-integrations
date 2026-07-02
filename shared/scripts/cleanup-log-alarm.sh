#!/bin/bash
# Clean up CloudWatch Log Alarm resources.
#
# Usage:
#   # Delete specific alarm stack
#   STACK_NAME=fsxn-log-alarm-sensitive-file-access \
#     bash shared/scripts/cleanup-log-alarm.sh
#
#   # Delete all log alarm stacks
#   bash shared/scripts/cleanup-log-alarm.sh --all
#
#   # Also delete SNS topic
#   STACK_NAME=fsxn-log-alarm-sensitive-file-access \
#   SNS_TOPIC_ARN=arn:aws:sns:ap-northeast-1:123456789012:fsxn-alerts \
#     bash shared/scripts/cleanup-log-alarm.sh --delete-sns
#
#   # Non-interactive mode (for CI/CD)
#   bash shared/scripts/cleanup-log-alarm.sh --all -y

set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
STACK_NAME="${STACK_NAME:-}"
DELETE_SNS=false
DELETE_ALL=false
CONFIRM=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --delete-sns) DELETE_SNS=true; shift ;;
    --all) DELETE_ALL=true; shift ;;
    -y) CONFIRM=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# --- Find stacks to delete ---
if [ "${DELETE_ALL}" = "true" ]; then
  echo "🔍 Finding all fsxn-log-alarm-* stacks..."
  STACKS=$(aws cloudformation list-stacks \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --query "StackSummaries[?starts_with(StackName, 'fsxn-log-alarm-')].StackName" \
    --output text 2>/dev/null)

  if [ -z "${STACKS}" ]; then
    echo "   No fsxn-log-alarm-* stacks found."
    exit 0
  fi

  echo "   Found: ${STACKS}"
elif [ -n "${STACK_NAME}" ]; then
  STACKS="${STACK_NAME}"
else
  echo "❌ Specify STACK_NAME or use --all"
  exit 1
fi

# --- Confirm ---
if [ "${CONFIRM}" != "true" ]; then
  echo ""
  echo "⚠️  This will delete the following stacks:"
  for stack in ${STACKS}; do
    echo "     - ${stack}"
  done
  echo ""
  read -p "Continue? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

# --- Delete stacks ---
for stack in ${STACKS}; do
  echo "🗑️  Deleting stack: ${stack}..."
  aws cloudformation delete-stack \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --stack-name "${stack}"

  echo "   Waiting for deletion..."
  aws cloudformation wait stack-delete-complete \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --stack-name "${stack}" 2>/dev/null || true

  echo "   ✅ ${stack} deleted"
done

# --- Optional: Delete SNS topic ---
if [ "${DELETE_SNS}" = "true" ] && [ -n "${SNS_TOPIC_ARN:-}" ]; then
  echo ""
  echo "🗑️  Deleting SNS topic: ${SNS_TOPIC_ARN}..."
  aws sns delete-topic \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --topic-arn "${SNS_TOPIC_ARN}"
  echo "   ✅ SNS topic deleted"
fi

echo ""
echo "✅ Cleanup complete"
