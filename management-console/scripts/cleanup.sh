#!/bin/bash
# ============================================================================
# FSx for ONTAP Management Console — Cleanup Script
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

Delete all FSx for ONTAP Management Console CloudFormation stacks in reverse
dependency order (monitoring → console → observability → auth → network).

Options:
  -y, --yes    Skip confirmation prompt (non-interactive mode)
  -h, --help   Show this help message and exit

Environment variables:
  AWS_REGION                AWS region (default: ap-northeast-1)
  FSXN_SECURITY_GROUP_ID   FSx for ONTAP file system security group ID (auto-removes access rules before deletion)

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

echo "=== FSx for ONTAP Management Console Cleanup ==="
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

# Remove FSx for ONTAP SG rules before stack deletion (prevents DELETE_FAILED)
if [[ -n "${FSXN_SECURITY_GROUP_ID:-}" ]]; then
  echo "  Removing FSx for ONTAP SG rules..."
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

# --- Helper: delete Route 53 record before console stack deletion -----------

cleanup_route53_record() {
  local console_stack="${STACK_PREFIX}-console"

  # Check if console stack exists
  if ! aws cloudformation describe-stacks \
    --stack-name "$console_stack" \
    --region "$AWS_REGION" > /dev/null 2>&1; then
    return 0
  fi

  # Get CustomDomainName parameter from the stack
  local custom_domain
  custom_domain=$(aws cloudformation describe-stacks \
    --stack-name "$console_stack" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Parameters[?ParameterKey=='CustomDomainName'].ParameterValue" \
    --output text 2>/dev/null || echo "")

  # Skip if no custom domain was configured
  if [[ -z "$custom_domain" || "$custom_domain" == "None" || "$custom_domain" == "" ]]; then
    return 0
  fi

  # Get HostedZoneId parameter from the stack
  local hosted_zone_id
  hosted_zone_id=$(aws cloudformation describe-stacks \
    --stack-name "$console_stack" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Parameters[?ParameterKey=='HostedZoneId'].ParameterValue" \
    --output text 2>/dev/null || echo "")

  if [[ -z "$hosted_zone_id" || "$hosted_zone_id" == "None" ]]; then
    return 0
  fi

  # Get ALB DNS name and hosted zone ID from stack outputs
  local alb_dns_name
  alb_dns_name=$(aws cloudformation describe-stacks \
    --stack-name "$console_stack" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" \
    --output text 2>/dev/null || echo "")

  local alb_hosted_zone_id
  alb_hosted_zone_id=$(aws cloudformation describe-stacks \
    --stack-name "$console_stack" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='AlbHostedZoneId'].OutputValue" \
    --output text 2>/dev/null || echo "")

  if [[ -z "$alb_dns_name" || "$alb_dns_name" == "None" || -z "$alb_hosted_zone_id" || "$alb_hosted_zone_id" == "None" ]]; then
    echo "  ⚠️  Could not retrieve ALB details for Route 53 cleanup, skipping."
    return 0
  fi

  # Check if the Route 53 record exists
  local record_exists
  record_exists=$(aws route53 list-resource-record-sets \
    --hosted-zone-id "$hosted_zone_id" \
    --query "ResourceRecordSets[?Name=='${custom_domain}.' && Type=='A'].Name" \
    --output text 2>/dev/null || echo "")

  if [[ -z "$record_exists" || "$record_exists" == "None" ]]; then
    echo "  ⏭️  Route 53 record for ${custom_domain} not found, skipping."
    return 0
  fi

  # Delete the Route 53 alias record
  echo "  Deleting Route 53 record: ${custom_domain} → ${alb_dns_name}..."
  aws route53 change-resource-record-sets \
    --hosted-zone-id "$hosted_zone_id" \
    --change-batch "{
      \"Changes\": [{
        \"Action\": \"DELETE\",
        \"ResourceRecordSet\": {
          \"Name\": \"${custom_domain}\",
          \"Type\": \"A\",
          \"AliasTarget\": {
            \"DNSName\": \"${alb_dns_name}\",
            \"HostedZoneId\": \"${alb_hosted_zone_id}\",
            \"EvaluateTargetHealth\": true
          }
        }
      }]
    }" > /dev/null 2>&1 && \
    echo "  ✅ Route 53 record deleted: ${custom_domain}" || \
    echo "  ⚠️  Failed to delete Route 53 record (may already be removed)."
}

# --- Execute cleanup --------------------------------------------------------

# Clean up Route 53 record before console stack deletion
echo "--- Pre-deletion: Route 53 cleanup ---"
cleanup_route53_record
echo ""

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
