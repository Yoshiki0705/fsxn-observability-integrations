#!/bin/bash
# ============================================================================
# Delete SHARED infrastructure for FSx for ONTAP Observability.
#
# WARNING: This deletes resources used by ALL vendor integrations.
#          Only run this AFTER all vendor-specific stacks have been removed.
#
# This script deletes:
#   1. fsxn-fp-srv — FPolicy ECS Fargate + SQS + EventBridge stack
#   2. fsxn-observability-prerequisites — S3 bucket + Access Point stack
#
# ============================================================================
# USAGE
# ============================================================================
#
#   bash shared/scripts/cleanup-shared.sh --confirm
#   bash shared/scripts/cleanup-shared.sh --confirm --skip-prerequisites
#   bash shared/scripts/cleanup-shared.sh --help
#
# The --confirm flag is REQUIRED. This is a destructive operation.
#
# ============================================================================
# WHAT GETS DELETED
# ============================================================================
#
#   Stack: fsxn-fp-srv
#     - ECS Fargate Service (FPolicy server)
#     - SQS Queue (FPolicy events)
#     - EventBridge Event Bus (fsxn-fpolicy-events)
#     - ECR repository (if created by stack)
#     - IAM roles and policies
#     - CloudWatch Log Groups
#
#   Stack: fsxn-observability-prerequisites
#     - S3 Bucket (audit logs) — DATA LOSS if bucket is not empty
#     - S3 Access Point
#     - EventBridge rules
#     - IAM roles
#
# ============================================================================

set -euo pipefail

# --- Configuration ----------------------------------------------------------

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
FPOLICY_STACK="${FPOLICY_STACK:-fsxn-fp-srv}"
PREREQ_STACK="${PREREQ_STACK:-fsxn-observability-prerequisites}"

# --- Parse arguments --------------------------------------------------------

CONFIRMED=false
SKIP_PREREQUISITES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) CONFIRMED=true; shift ;;
    --skip-prerequisites) SKIP_PREREQUISITES=true; shift ;;
    -h|--help)
      echo "Usage: $0 --confirm [OPTIONS]"
      echo ""
      echo "Delete shared FSx for ONTAP observability infrastructure."
      echo ""
      echo "Options:"
      echo "  --confirm              Required. Confirms destructive operation."
      echo "  --skip-prerequisites   Skip deletion of the prerequisites stack"
      echo "                         (S3 bucket + Access Point)"
      echo ""
      echo "Environment variables:"
      echo "  AWS_REGION         AWS region (default: ap-northeast-1)"
      echo "  FPOLICY_STACK      FPolicy stack name (default: fsxn-fp-srv)"
      echo "  PREREQ_STACK       Prerequisites stack name"
      echo "                     (default: fsxn-observability-prerequisites)"
      echo ""
      echo "This deletes resources shared by ALL vendor integrations."
      echo "Run vendor-specific cleanup first:"
      echo "  bash integrations/<vendor>/scripts/cleanup.sh --all"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# --- Safety check -----------------------------------------------------------

if [ "$CONFIRMED" != true ]; then
  echo "ERROR: --confirm flag is required for this destructive operation."
  echo ""
  echo "This will delete:"
  echo "  - ${FPOLICY_STACK} (FPolicy ECS Fargate + SQS + EventBridge)"
  if [ "$SKIP_PREREQUISITES" != true ]; then
    echo "  - ${PREREQ_STACK} (S3 bucket + Access Point)"
    echo ""
    echo "  S3 bucket deletion will PERMANENTLY DESTROY all audit log data."
  fi
  echo ""
  echo "Run with --confirm to proceed:"
  echo "  bash shared/scripts/cleanup-shared.sh --confirm"
  exit 1
fi

# --- Display plan -----------------------------------------------------------

echo "============================================================"
echo "  SHARED INFRASTRUCTURE DELETION"
echo "============================================================"
echo ""
echo "Region: ${AWS_REGION}"
echo ""
echo "The following shared stacks will be PERMANENTLY deleted:"
echo ""
echo "  1. ${FPOLICY_STACK}"
echo "     - ECS Fargate Service (FPolicy server)"
echo "     - SQS Queue (FPolicy events)"
echo "     - EventBridge Event Bus"
echo "     - IAM roles, CloudWatch Log Groups"
echo ""
if [ "$SKIP_PREREQUISITES" != true ]; then
  echo "  2. ${PREREQ_STACK}"
  echo "     - S3 Bucket (audit logs) — ALL DATA WILL BE LOST"
  echo "     - S3 Access Point"
  echo "     - EventBridge rules"
  echo "     - IAM roles"
  echo ""
fi
echo "============================================================"
echo ""
read -p "Type 'DELETE' to confirm permanent deletion: " CONFIRM_TEXT
if [ "$CONFIRM_TEXT" != "DELETE" ]; then
  echo "Aborted. You must type 'DELETE' exactly."
  exit 0
fi
echo ""

# --- Helper: delete a CloudFormation stack ----------------------------------

delete_stack() {
  local stack_name="$1"
  local description="${2:-}"
  echo "--- Deleting: ${stack_name}${description:+ ($description)} ---"

  if ! aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "  Does not exist, skipping."
    return 0
  fi

  local status
  status=$(aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" \
    --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "UNKNOWN")

  if [ "$status" = "DELETE_FAILED" ]; then
    echo "  Stack is in DELETE_FAILED state."
    echo "  Check CloudFormation console for details."
    echo "  Common fix: empty S3 bucket first, then retry."
    echo "    aws s3 rm s3://<bucket-name> --recursive"
    echo "    aws cloudformation delete-stack --stack-name ${stack_name} --region ${AWS_REGION}"
    return 1
  fi

  echo "  Status: ${status}"
  echo "  Initiating deletion..."
  aws cloudformation delete-stack \
    --stack-name "$stack_name" \
    --region "$AWS_REGION"

  echo "  Waiting for deletion (may take several minutes)..."
  if ! aws cloudformation wait stack-delete-complete \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" 2>/dev/null; then
    echo "  Deletion failed or timed out."
    echo "  Check: aws cloudformation describe-stack-events --stack-name ${stack_name} --region ${AWS_REGION}"
    return 1
  fi

  echo "  Deleted: ${stack_name}"
}

# --- Execute ----------------------------------------------------------------

echo "=== Step 1: FPolicy Fargate Stack ==="
delete_stack "$FPOLICY_STACK" "ECS Fargate + SQS + EventBridge"

if [ "$SKIP_PREREQUISITES" != true ]; then
  echo ""
  echo "=== Step 2: Prerequisites Stack ==="
  echo "  Note: If the S3 bucket is not empty, deletion will fail."
  echo "  You may need to empty it first with: aws s3 rm s3://<bucket> --recursive"
  echo ""
  delete_stack "$PREREQ_STACK" "S3 bucket + Access Point"
fi

# --- Summary ----------------------------------------------------------------

echo ""
echo "============================================================"
echo "  Shared Infrastructure Cleanup Complete"
echo "============================================================"
echo ""
echo "All FSx for ONTAP observability resources have been removed."
echo ""
echo "To redeploy from scratch:"
echo "  1. bash shared/scripts/deploy.sh prerequisites"
echo "  2. bash shared/scripts/fpolicy-fargate-control.sh start"
echo "  3. bash integrations/<vendor>/scripts/deploy.sh"
