#!/bin/bash
# Deploy CloudWatch Log Alarm for FSx for ONTAP audit logs.
#
# This script deploys the cloudwatch-log-alarm.yaml CloudFormation template.
# AWS CLI does NOT have `put-log-alarm` as of July 2026 (CLI v2.35.x),
# so CloudFormation is the recommended deployment method.
#
# Prerequisites:
#   - FSx for ONTAP admin audit logs flowing to CloudWatch Logs
#     (deploy syslog-vpce-cloudwatch.yaml first)
#   - SNS topic for alarm notifications
#
# Usage:
#   # Sensitive file access detection (threshold=0 means any access triggers alarm)
#   DETECTION_TYPE=sensitive-file-access \
#   TARGET_PATTERN="/vol/data/confidential" \
#   SNS_TOPIC_ARN=arn:aws:sns:ap-northeast-1:123456789012:fsxn-alerts \
#     bash shared/scripts/deploy-log-alarm.sh
#
#   # Failed access detection (threshold=10 means 10+ failures trigger alarm)
#   DETECTION_TYPE=failed-access-attempts \
#   ALARM_THRESHOLD=10 \
#   SNS_TOPIC_ARN=arn:aws:sns:ap-northeast-1:123456789012:fsxn-alerts \
#     bash shared/scripts/deploy-log-alarm.sh
#
#   # Create SNS topic automatically
#   DETECTION_TYPE=bulk-delete-operations \
#   ALARM_THRESHOLD=50 \
#   CREATE_SNS_TOPIC=true \
#   SNS_TOPIC_NAME=fsxn-security-alerts \
#     bash shared/scripts/deploy-log-alarm.sh
#
# E2E Validation Notes (2026-07-02):
#   - AWS::CloudWatch::LogAlarm is supported in CloudFormation (confirmed)
#   - cfn-lint E3006 is expected (resource type not yet in cfn-lint spec)
#   - State transitions: INSUFFICIENT_DATA → OK → ALARM (normal flow)
#   - First evaluation takes ~5-10 min after stack creation
#   - Console shows alarm as "Log alarm" type (distinct from "Metric alarm")

set -euo pipefail

# --- Configuration ---
AWS_REGION="${AWS_REGION:-ap-northeast-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
LOG_GROUP_NAME="${LOG_GROUP_NAME:-/syslog/fsxn-admin-audit}"
DETECTION_TYPE="${DETECTION_TYPE:-sensitive-file-access}"
TARGET_PATTERN="${TARGET_PATTERN:-/vol/data/confidential}"
ALARM_THRESHOLD="${ALARM_THRESHOLD:-0}"
EVALUATION_FREQUENCY="${EVALUATION_FREQUENCY:-5}"
QUERY_RESULTS_TO_EVALUATE="${QUERY_RESULTS_TO_EVALUATE:-3}"
QUERY_RESULTS_TO_ALARM="${QUERY_RESULTS_TO_ALARM:-1}"
ACTION_LOG_LINE_COUNT="${ACTION_LOG_LINE_COUNT:-5}"
STACK_NAME="${STACK_NAME:-fsxn-log-alarm-${DETECTION_TYPE}}"
CREATE_SNS_TOPIC="${CREATE_SNS_TOPIC:-false}"
SNS_TOPIC_NAME="${SNS_TOPIC_NAME:-fsxn-log-alarm-notifications}"

# Template path (relative to repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../templates/cloudwatch-log-alarm.yaml"

# --- Validation ---
if [ ! -f "${TEMPLATE_FILE}" ]; then
  echo "❌ Template not found: ${TEMPLATE_FILE}"
  echo "   Run this script from the repository root."
  exit 1
fi

if [ "${CREATE_SNS_TOPIC}" = "true" ]; then
  echo "📧 Creating SNS topic: ${SNS_TOPIC_NAME}..."
  SNS_TOPIC_ARN=$(aws sns create-topic \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --name "${SNS_TOPIC_NAME}" \
    --query "TopicArn" --output text)
  echo "   Topic ARN: ${SNS_TOPIC_ARN}"
  echo ""
  echo "   ⚠️  Remember to confirm the SNS subscription in your email!"
  echo ""
elif [ -z "${SNS_TOPIC_ARN:-}" ]; then
  echo "❌ SNS_TOPIC_ARN is required."
  echo "   Set SNS_TOPIC_ARN=arn:aws:sns:... or use CREATE_SNS_TOPIC=true"
  exit 1
fi

# --- Deploy ---
echo "🚀 Deploying CloudWatch Log Alarm..."
echo "   Stack:      ${STACK_NAME}"
echo "   Region:     ${AWS_REGION}"
echo "   Log Group:  ${LOG_GROUP_NAME}"
echo "   Detection:  ${DETECTION_TYPE}"
echo "   Pattern:    ${TARGET_PATTERN}"
echo "   Threshold:  > ${ALARM_THRESHOLD}"
echo "   Frequency:  every ${EVALUATION_FREQUENCY} min"
echo "   Evaluation: ${QUERY_RESULTS_TO_ALARM} of ${QUERY_RESULTS_TO_EVALUATE}"
echo "   Log lines:  ${ACTION_LOG_LINE_COUNT} lines in notifications"
echo ""

aws cloudformation deploy \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --template-file "${TEMPLATE_FILE}" \
  --stack-name "${STACK_NAME}" \
  --parameter-overrides \
    LogGroupName="${LOG_GROUP_NAME}" \
    DetectionType="${DETECTION_TYPE}" \
    TargetPattern="${TARGET_PATTERN}" \
    AlarmThreshold="${ALARM_THRESHOLD}" \
    EvaluationFrequencyMinutes="${EVALUATION_FREQUENCY}" \
    QueryResultsToEvaluate="${QUERY_RESULTS_TO_EVALUATE}" \
    QueryResultsToAlarm="${QUERY_RESULTS_TO_ALARM}" \
    AlarmSnsTopicArn="${SNS_TOPIC_ARN}" \
    ActionLogLineCount="${ACTION_LOG_LINE_COUNT}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

# --- Output ---
echo ""
echo "✅ Deployment complete!"
echo ""

OUTPUTS=$(aws cloudformation describe-stacks \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs" \
  --output json 2>/dev/null)

ALARM_NAME=$(echo "${OUTPUTS}" | python3 -c "
import sys, json
outputs = json.load(sys.stdin)
for o in outputs:
    if o['OutputKey'] == 'AlarmName':
        print(o['OutputValue'])
        break
" 2>/dev/null || echo "unknown")

echo "   Alarm Name: ${ALARM_NAME}"
echo "   Console:    https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#alarmsV2:alarm/${ALARM_NAME}"
echo ""
echo "📋 Next steps:"
echo "   1. Confirm SNS email subscription (check inbox)"
echo "   2. Wait ~5-10 min for first scheduled query execution"
echo "   3. Alarm transitions: INSUFFICIENT_DATA → OK → ALARM"
echo "   4. Verify in CloudWatch Console → Alarms → '${ALARM_NAME}'"
echo ""
echo "🧪 To test alarm firing:"
echo "   Generate matching log entries via ONTAP CLI operations,"
echo "   then wait for the next evaluation cycle (${EVALUATION_FREQUENCY} min)."
