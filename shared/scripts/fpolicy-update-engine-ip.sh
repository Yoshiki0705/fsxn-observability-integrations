#!/bin/bash
set -euo pipefail

# FPolicy External Engine IP Updater
#
# When the Fargate task restarts, it gets a new private IP.
# This script updates the ONTAP FPolicy External Engine with the new IP.
#
# IMPORTANT: Updating the engine requires temporarily disabling the FPolicy
# policy. Events generated during this window will NOT be captured.
#
# Usage:
#   ./fpolicy-update-engine-ip.sh [--auto]
#
# With --auto: Automatically detects the current Fargate task IP
# Without:     Prompts for the new IP address
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - ONTAP fsxadmin credentials in Secrets Manager
#   - Network access to ONTAP management endpoint (via bastion or VPN)

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
ECS_CLUSTER="${ECS_CLUSTER:-fsxn-fpolicy-server-cluster}"
ECS_SERVICE="${ECS_SERVICE:-fsxn-fpolicy-server-service}"
ONTAP_MGMT_IP="${ONTAP_MGMT_IP:?ERROR: Set ONTAP_MGMT_IP to your FSx for ONTAP management endpoint IP}"
ONTAP_SECRET_ID="${ONTAP_SECRET_ID:-fsx-ontap-fsxadmin-credentials}"
SVM_UUID="${SVM_UUID:?ERROR: Set SVM_UUID to your SVM UUID (from ONTAP REST API /api/svm/svms)}"
ENGINE_NAME="${ENGINE_NAME:-fpolicy_aws_engine}"
POLICY_NAME="${POLICY_NAME:-fpolicy_aws}"

# Bastion configuration (set these if ONTAP is only reachable via bastion)
BASTION_IP="${BASTION_IP:-}"
BASTION_KEY="${BASTION_KEY:-}"
BASTION_USER="${BASTION_USER:-ec2-user}"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o PubkeyAcceptedAlgorithms=+ssh-rsa -o HostkeyAlgorithms=+ssh-rsa"

get_fargate_task_ip() {
  local task_arn
  task_arn=$(aws ecs list-tasks \
    --cluster "${ECS_CLUSTER}" \
    --service-name "${ECS_SERVICE}" \
    --desired-status RUNNING \
    --query "taskArns[0]" \
    --output text \
    --region "${AWS_REGION}")

  if [[ "${task_arn}" == "None" || -z "${task_arn}" ]]; then
    echo "ERROR: No running Fargate tasks found" >&2
    exit 1
  fi

  aws ecs describe-tasks \
    --cluster "${ECS_CLUSTER}" \
    --tasks "${task_arn}" \
    --query "tasks[0].containers[0].networkInterfaces[0].privateIpv4Address" \
    --output text \
    --region "${AWS_REGION}"
}

update_engine_ip() {
  local new_ip="$1"
  local ontap_pass

  ontap_pass=$(aws secretsmanager get-secret-value \
    --secret-id "${ONTAP_SECRET_ID}" \
    --region "${AWS_REGION}" \
    --query "SecretString" \
    --output text | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['password'])")

  # Helper: run curl either via bastion or directly
  _ontap_curl() {
    if [[ -n "${BASTION_IP}" && -n "${BASTION_KEY}" ]]; then
      ssh -i "${BASTION_KEY}" ${SSH_OPTS} "${BASTION_USER}@${BASTION_IP}" \
        "curl -sk $*" > /dev/null
    else
      curl -sk "$@" > /dev/null
    fi
  }

  echo "📋 Step 1/3: Disabling FPolicy policy '${POLICY_NAME}'..."
  _ontap_curl -X PATCH -u "fsxadmin:${ontap_pass}" \
    -H 'Content-Type: application/json' \
    -d "{\"enabled\": false}" \
    "https://${ONTAP_MGMT_IP}/api/protocols/fpolicy/${SVM_UUID}/policies/${POLICY_NAME}"

  echo "📋 Step 2/3: Updating engine '${ENGINE_NAME}' → ${new_ip}..."
  _ontap_curl -X PATCH -u "fsxadmin:${ontap_pass}" \
    -H 'Content-Type: application/json' \
    -d "{\"primary_servers\": [\"${new_ip}\"]}" \
    "https://${ONTAP_MGMT_IP}/api/protocols/fpolicy/${SVM_UUID}/engines/${ENGINE_NAME}"

  echo "📋 Step 3/3: Re-enabling FPolicy policy '${POLICY_NAME}'..."
  _ontap_curl -X PATCH -u "fsxadmin:${ontap_pass}" \
    -H 'Content-Type: application/json' \
    -d "{\"enabled\": true, \"priority\": 1}" \
    "https://${ONTAP_MGMT_IP}/api/protocols/fpolicy/${SVM_UUID}/policies/${POLICY_NAME}"

  echo ""
  echo "✅ FPolicy External Engine updated to ${new_ip}"
  echo "   ONTAP will reconnect within ~30 seconds (keep_alive_interval: PT2M)"
}

# Main
echo "=== FPolicy External Engine IP Updater ==="
echo ""

if [[ "${1:-}" == "--auto" ]]; then
  echo "🔍 Auto-detecting Fargate task IP..."
  NEW_IP=$(get_fargate_task_ip)
  echo "   Detected: ${NEW_IP}"
else
  if [[ -n "${1:-}" ]]; then
    NEW_IP="$1"
  else
    echo "🔍 Current Fargate task IP:"
    get_fargate_task_ip
    echo ""
    read -rp "Enter new IP for FPolicy engine: " NEW_IP
  fi
fi

echo ""
read -rp "Update FPolicy engine to ${NEW_IP}? [y/N] " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo ""
update_engine_ip "${NEW_IP}"
