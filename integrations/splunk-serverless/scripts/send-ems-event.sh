#!/usr/bin/env bash
# send-ems-event.sh — Send arw.volume.state EMS event to API Gateway for ransomware detection demo
#
# Usage:
#   ./send-ems-event.sh [--endpoint URL] [--api-key KEY] [--region REGION] [--stack-name NAME]
#
# Environment Variables:
#   EMS_API_ENDPOINT    - API Gateway endpoint URL (auto-detected from stack if not set)
#   EMS_API_KEY         - API key for x-api-key header (auto-detected from Secrets Manager if not set)
#   AWS_REGION          - AWS region (default: ap-northeast-1)
#   STACK_NAME          - CloudFormation stack name (default: fsxn-splunk-integration)
#
# This script sends a simulated ONTAP Anti-Ransomware Protection (ARP) EMS event
# to the deployed API Gateway endpoint, demonstrating the ransomware detection
# pipeline: ONTAP EMS → API Gateway → Lambda → Splunk HEC.

set -euo pipefail

# --- Configuration ---
REGION="${AWS_REGION:-ap-northeast-1}"
STACK_NAME="${STACK_NAME:-fsxn-splunk-integration}"
EMS_ENDPOINT="${EMS_API_ENDPOINT:-}"
API_KEY="${EMS_API_KEY:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --endpoint)
      EMS_ENDPOINT="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --stack-name)
      STACK_NAME="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--endpoint URL] [--api-key KEY] [--region REGION] [--stack-name NAME]"
      echo ""
      echo "Send arw.volume.state EMS event for ransomware detection demo."
      echo ""
      echo "Options:"
      echo "  --endpoint      API Gateway endpoint URL"
      echo "  --api-key       API key for authentication"
      echo "  --region        AWS region (default: ap-northeast-1)"
      echo "  --stack-name    CloudFormation stack name (default: fsxn-splunk-integration)"
      echo "  -h, --help      Show this help message"
      echo ""
      echo "If --endpoint or --api-key are not provided, they will be auto-detected"
      echo "from the CloudFormation stack outputs and Secrets Manager."
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1"
      exit 1
      ;;
  esac
done

# --- Preflight checks ---
echo "=== Demo Scenario 2: Ransomware Detection (ARP EMS Event) ==="
echo ""

# Check required tools
if ! command -v aws &> /dev/null; then
  echo "ERROR: AWS CLI is not installed or not in PATH"
  exit 1
fi

if ! command -v curl &> /dev/null; then
  echo "ERROR: curl is not installed or not in PATH"
  exit 1
fi

# --- Step 1: Resolve API Gateway endpoint ---
if [[ -z "${EMS_ENDPOINT}" ]]; then
  echo "Step 1: Auto-detecting API Gateway endpoint from stack '${STACK_NAME}'..."
  EMS_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[?OutputKey==`EmsApiEndpoint`].OutputValue' \
    --output text 2>/dev/null || echo "")

  if [[ -z "${EMS_ENDPOINT}" || "${EMS_ENDPOINT}" == "None" ]]; then
    echo "ERROR: Could not auto-detect API Gateway endpoint from stack '${STACK_NAME}'"
    echo "  Provide --endpoint manually or check stack deployment status"
    exit 1
  fi
  echo "  Endpoint: ${EMS_ENDPOINT}"
else
  echo "Step 1: Using provided endpoint: ${EMS_ENDPOINT}"
fi

# --- Step 2: Resolve API key ---
if [[ -z "${API_KEY}" ]]; then
  echo "Step 2: Auto-detecting API key from Secrets Manager..."
  API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id "ems-webhook-api-key" \
    --region "${REGION}" \
    --query 'SecretString' \
    --output text 2>/dev/null || echo "")

  if [[ -z "${API_KEY}" ]]; then
    echo "ERROR: Could not retrieve API key from Secrets Manager"
    echo "  Secret ID: ems-webhook-api-key"
    echo "  Provide --api-key manually"
    exit 1
  fi
  echo "  API key: ****${API_KEY: -4}"
else
  echo "Step 2: Using provided API key: ****${API_KEY: -4}"
fi

echo ""
echo "Configuration:"
echo "  Region:    ${REGION}"
echo "  Stack:     ${STACK_NAME}"
echo "  Endpoint:  ${EMS_ENDPOINT}"
echo ""

# --- Step 3: Send EMS event ---
echo "Step 3: Sending arw.volume.state EMS event..."
echo ""

# Generate current timestamp
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# EMS event payload (ARP ransomware detection)
PAYLOAD=$(cat <<EOF
{
  "message-name": "arw.volume.state",
  "message-severity": "alert",
  "message-timestamp": "${TIMESTAMP}",
  "parameters": {
    "volume-name": "vol_data",
    "vserver-name": "svm-prod-01",
    "state": "attack-detected",
    "attack-type": "ransomware",
    "suspect-files-count": "47",
    "snapshot-name": "Anti_ransomware_backup_$(date +%Y-%m-%d_%H%M)",
    "description": "Autonomous Ransomware Protection has detected suspicious file activity on volume vol_data. A protective snapshot has been created automatically."
  }
}
EOF
)

echo "Payload:"
echo "${PAYLOAD}" | python3 -m json.tool 2>/dev/null || echo "${PAYLOAD}"
echo ""

# Send the request
HTTP_CODE=$(curl -s -o /tmp/ems-response.json -w "%{http_code}" \
  -X POST "${EMS_ENDPOINT}/ems" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d "${PAYLOAD}")

echo "HTTP Response Code: ${HTTP_CODE}"
echo "Response Body:"
cat /tmp/ems-response.json 2>/dev/null || echo "(empty)"
echo ""
echo ""

# --- Step 4: Evaluate result ---
if [[ "${HTTP_CODE}" == "200" ]]; then
  echo "✅ EMS event sent successfully (HTTP 200)"
elif [[ "${HTTP_CODE}" == "401" ]]; then
  echo "❌ Authentication failed (HTTP 401)"
  echo "  Check: x-api-key value matches Secrets Manager secret"
  rm -f /tmp/ems-response.json
  exit 1
elif [[ "${HTTP_CODE}" == "400" ]]; then
  echo "❌ Bad request (HTTP 400)"
  echo "  Check: EMS payload contains required fields (message-name, message-severity, message-timestamp)"
  rm -f /tmp/ems-response.json
  exit 1
elif [[ "${HTTP_CODE}" == "502" ]]; then
  echo "❌ Bad gateway (HTTP 502)"
  echo "  Check: Splunk HEC endpoint is reachable and HEC token is valid"
  rm -f /tmp/ems-response.json
  exit 1
else
  echo "❌ Unexpected response (HTTP ${HTTP_CODE})"
  rm -f /tmp/ems-response.json
  exit 1
fi

# --- Step 5: Provide Splunk verification query ---
echo ""
echo "=== Next Steps ==="
echo ""
echo "Step 5: Verify in Splunk Search with the following SPL query:"
echo ""
echo "  index=fsxn_ems sourcetype=fsxn:ontap:ems message-name=arw.volume.state"
echo ""
echo "Expected: At least 1 event with message-name=arw.volume.state should appear."
echo ""
echo "Fields to verify:"
echo "  - message-name: arw.volume.state"
echo "  - message-severity: alert"
echo "  - parameters.state: attack-detected"
echo "  - parameters.suspect-files-count: 47"
echo ""
echo "Screenshot: Save as docs/screenshots/splunk/splunk-ransomware-detection-$(date +%Y%m%d).png"
echo ""

# Cleanup
rm -f /tmp/ems-response.json

echo "=== Demo Scenario 2 Complete ==="
