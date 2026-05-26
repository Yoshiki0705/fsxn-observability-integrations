#!/bin/bash
# ============================================================================
# FSxN Management Console — Cleanup Script
#
# Deletes all 5 CloudFormation stacks in reverse dependency order:
#   monitoring → console → observability → auth → network
#
# Usage:
#   bash scripts/cleanup.sh          # Interactive (prompts for confirmation)
#   bash scripts/cleanup.sh -y       # Non-interactive (skip confirmation)
#   bash scripts/cleanup.sh --help   # Show usage
#
# Requirements: 11.5, 11.8
# ============================================================================

set -euo pipefail

# --- Configuration ----------------------------------------------------------

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
STACK_PREFIX="fsxn-mgmt"

# Stacks in reverse dependency order (deletion order)
STACKS=(
  "${STACK_PREFIX}-monitoring"
  "${STACK_PREFIX}-console"
  "${STACK_PREFIX}-observability"
  "${STACK_PREFIX}-auth"
  "${STACK_PREFIX}-network"
)

# --- Parse arguments --------------------------------------------------------

SKIP_CONFIRM=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)
      SKIP_CONFIRM=true
      shift
      ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Delete all FSxN Management Console CloudFormation stacks in reverse
dependency order (monitoring → console → observability → auth → network).

Options:
  -y, --yes    Skip confirmation prompt (non-interactive mode)
  -h, --help   Show this help message and exit

Environment variables:
  AWS_REGION                AWS region (default: ap-northeast-1)
  FSXN_SECURITY_GROUP_ID   FSx ONTAP file system security group ID (auto-removes access rules before deletion)

Deletion order:
  1. ${STACK_PREFIX}-monitoring     (CloudWatch alarms, dashboard, SNS)
  2. ${STACK_PREFIX}-console        (ToolJet ECS, ALB, RDS, Lambda)
  3. ${STACK_PREFIX}-observability  (AMP, AMG, Harvest ECS, ADOT)
  4. ${STACK_PREFIX}-auth           (Cognito User Pool, App Client)
  5. ${STACK_PREFIX}-network        (VPC Endpoints, NAT GW, SGs)

Exit codes:
  0   All stacks deleted successfully
  1   One or more stacks failed to delete

Examples:
  $(basename "$0")           # Interactive mode
  $(basename "$0") -y        # CI/CD non-interactive mode
EOF
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1"
      echo "Run '$(basename "$0") --help' for usage."
      exit 1
      ;;
  esac
done

# --- Confirmation -----------------------------------------------------------

echo "=== FSxN Management Console Cleanup ==="
echo ""
echo "Region: ${AWS_REGION}"
echo "Stack prefix: ${STACK_PREFIX}"
echo ""
echo "Stacks to delete (reverse dependency order):"
echo "  1. ${STACK_PREFIX}-monitoring     (CloudWatch alarms, dashboard, SNS)"
echo "  2. ${STACK_PREFIX}-console        (ToolJet ECS, ALB, RDS, Lambda)"
echo "  3. ${STACK_PREFIX}-observability  (AMP, AMG, Harvest ECS, ADOT)"
echo "  4. ${STACK_PREFIX}-auth           (Cognito User Pool, App Client)"
echo "  5. ${STACK_PREFIX}-network        (VPC Endpoints, NAT GW, SGs)"
echo ""

if [ "$SKIP_CONFIRM" != true ]; then
  read -p "Proceed with cleanup? (y/N): " CONFIRM
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
  echo ""
fi

# Remove FSx ONTAP SG rules before stack deletion (prevents DELETE_FAILED)
if [[ -n "${FSXN_SECURITY_GROUP_ID:-}" ]]; then
  echo "  Removing FSx ONTAP SG rules..."
  # Get all task SG IDs from the network stack (if it exists)
  for sg_output in HarvestTaskSgId ToolJetTaskSgId; do
    SG_ID=$(aws cloudformation describe-stacks \
      --stack-name "${STACK_PREFIX}-network" \
      --query "Stacks[0].Outputs[?OutputKey=='${sg_output}'].OutputValue" \
      --output text --region "${AWS_REGION}" 2>/dev/null || echo "")
    if [[ -n "$SG_ID" && "$SG_ID" != "None" ]]; then
      aws ec2 revoke-security-group-ingress \
        --group-id "${FSXN_SECURITY_GROUP_ID}" \
        --protocol tcp --port 443 \
        --source-group "$SG_ID" \
        --region "${AWS_REGION}" 2>/dev/null || true
      echo "    Removed: ${FSXN_SECURITY_GROUP_ID} ← ${SG_ID}:443"
    fi
  done
fi

# --- Helper: report retained resources on DELETE_FAILED ---------------------

report_retained_resources() {
  local stack_name="$1"

  echo ""
  echo "  Retained resources for ${stack_name}:"

  local resources
  resources=$(aws cloudformation describe-stack-resources \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" \
    --query "StackResources[?ResourceStatus=='DELETE_FAILED'].[LogicalResourceId,ResourceType,ResourceStatusReason]" \
    --output text 2>/dev/null || echo "")

  if [ -z "$resources" ]; then
    # Fall back to listing all non-deleted resources
    resources=$(aws cloudformation describe-stack-resources \
      --stack-name "$stack_name" \
      --region "$AWS_REGION" \
      --query "StackResources[?ResourceStatus!='DELETE_COMPLETE'].[LogicalResourceId,ResourceType,ResourceStatus]" \
      --output text 2>/dev/null || echo "")
  fi

  if [ -n "$resources" ]; then
    echo "$resources" | while IFS=$'\t' read -r logical_id resource_type reason; do
      echo "    - ${logical_id} (${resource_type}): ${reason:-no reason provided}"
    done
  else
    echo "    (no retained resources found)"
  fi

  echo ""
  echo "  To retry deletion:"
  echo "    aws cloudformation delete-stack --stack-name ${stack_name} --region ${AWS_REGION}"
  echo ""
  echo "  To inspect events:"
  echo "    aws cloudformation describe-stack-events --stack-name ${stack_name} --region ${AWS_REGION} \\"
  echo "      --query 'StackEvents[?ResourceStatus==\`DELETE_FAILED\`]'"
}

# --- Helper: delete a stack and wait for completion -------------------------

FAILED_STACKS=()

delete_stack() {
  local stack_name="$1"
  local step_num="$2"
  local total="${#STACKS[@]}"

  echo "--- Step ${step_num}/${total}: ${stack_name} ---"

  # Check if stack exists
  if ! aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "  ⏭️  Does not exist, skipping."
    echo ""
    return 0
  fi

  # Check current status
  local status
  status=$(aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" \
    --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "UNKNOWN")

  # Handle DELETE_FAILED state
  if [ "$status" = "DELETE_FAILED" ]; then
    echo "  ❌ Stack is in DELETE_FAILED state."
    report_retained_resources "$stack_name"
    FAILED_STACKS+=("$stack_name")
    echo ""
    return 1
  fi

  # Initiate deletion
  echo "  Deleting: ${stack_name} (current status: ${status})..."
  aws cloudformation delete-stack \
    --stack-name "$stack_name" \
    --region "$AWS_REGION"

  # Wait for deletion to complete
  echo "  Waiting for deletion to complete..."
  if ! aws cloudformation wait stack-delete-complete \
    --stack-name "$stack_name" \
    --region "$AWS_REGION" 2>/dev/null; then

    # Check if it ended up in DELETE_FAILED
    local final_status
    final_status=$(aws cloudformation describe-stacks \
      --stack-name "$stack_name" \
      --region "$AWS_REGION" \
      --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "DELETED")

    if [ "$final_status" = "DELETE_FAILED" ]; then
      echo "  ❌ Stack deletion failed: ${stack_name}"
      report_retained_resources "$stack_name"
      FAILED_STACKS+=("$stack_name")
      echo ""
      return 1
    fi
  fi

  echo "  ✅ Deleted: ${stack_name}"
  echo ""
  return 0
}

# --- Execute cleanup --------------------------------------------------------

for i in "${!STACKS[@]}"; do
  step=$((i + 1))
  delete_stack "${STACKS[$i]}" "$step" || true
done

# --- Summary ----------------------------------------------------------------

echo "=== Cleanup Summary ==="
echo ""

if [ ${#FAILED_STACKS[@]} -eq 0 ]; then
  echo "✅ All stacks deleted successfully."
  exit 0
else
  echo "❌ The following stacks failed to delete:"
  for stack in "${FAILED_STACKS[@]}"; do
    echo "  - ${stack}"
  done
  echo ""
  echo "Resolve retained resources and retry deletion manually."
  exit 1
fi
