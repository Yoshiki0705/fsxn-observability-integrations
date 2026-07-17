#!/bin/bash
# Dynatrace — Create FSx for ONTAP Log Metric Events (Alerts)
#
# Creates 3 custom log metric events:
#   1. Ransomware Detection (ARP EMS event)
#   2. Mass File Deletion (>100 deletes in 5min)
#   3. Failed Access Spike (>50 failures in 5min)
#
# Threshold customization:
#   Edit the "threshold" values in metric event payloads below.
#   Detection rationale: docs/en/detection-use-cases.md
#
# Prerequisites:
#   - Dynatrace API Token with scope: metrics.ingest, settings.write
#   - Logs flowing with log.source = "fsxn"
#
# Usage:
#   export DT_ENV_URL="https://<env-id>.live.dynatrace.com"
#   export DT_API_TOKEN="<your-api-token>"
#   bash integrations/dynatrace/scripts/create-alerts.sh

set -euo pipefail

DT_ENV_URL="${DT_ENV_URL:-}"
DT_API_TOKEN="${DT_API_TOKEN:-}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Dynatrace — Create FSx for ONTAP Alerts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${DT_ENV_URL}" ] || [ -z "${DT_API_TOKEN}" ]; then
  echo "❌ ERROR: DT_ENV_URL and DT_API_TOKEN must be set."
  exit 1
fi

create_metric_event() {
  local payload="$1"
  local name="$2"

  echo "  Creating: ${name}..."

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${DT_ENV_URL}/api/v2/settings/objects" \
    -H "Content-Type: application/json" \
    -H "Authorization: Api-Token ${DT_API_TOKEN}" \
    -d "[${payload}]")

  if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "201" ]; then
    echo "    ✅ Created"
  elif [ "${HTTP_CODE}" = "409" ]; then
    echo "    ⚠️  Already exists"
  else
    echo "    ❌ Failed (HTTP ${HTTP_CODE})"
  fi
}

echo ""

create_metric_event '{
  "schemaId": "builtin:anomaly-detection.metric-events",
  "scope": "environment",
  "value": {
    "summary": "FSxN: Ransomware Detection (ARP)",
    "description": "ONTAP ARP/AI detected ransomware-like activity",
    "enabled": true,
    "eventType": "CUSTOM_ALERT",
    "alertCondition": "ABOVE",
    "samples": 1,
    "violatingSamples": 1,
    "dealertingSamples": 3,
    "threshold": 0,
    "queryDefinition": {
      "type": "LOG",
      "logQuery": "log.source=\"fsxn\" AND (content=\"arw\" OR content=\"ARP\")",
      "aggregation": "COUNT"
    }
  }
}' "Ransomware Detection (ARP)"

create_metric_event '{
  "schemaId": "builtin:anomaly-detection.metric-events",
  "scope": "environment",
  "value": {
    "summary": "FSxN: Mass File Deletion (>100 in 5min)",
    "description": "A user deleted more than 100 files in 5 minutes",
    "enabled": true,
    "eventType": "CUSTOM_ALERT",
    "alertCondition": "ABOVE",
    "samples": 1,
    "violatingSamples": 1,
    "dealertingSamples": 3,
    "threshold": 100,
    "queryDefinition": {
      "type": "LOG",
      "logQuery": "log.source=\"fsxn\" AND content=\"Delete\"",
      "aggregation": "COUNT"
    }
  }
}' "Mass File Deletion"

create_metric_event '{
  "schemaId": "builtin:anomaly-detection.metric-events",
  "scope": "environment",
  "value": {
    "summary": "FSxN: Failed Access Spike (>50 in 5min)",
    "description": "More than 50 failed access attempts in 5 minutes",
    "enabled": true,
    "eventType": "CUSTOM_ALERT",
    "alertCondition": "ABOVE",
    "samples": 1,
    "violatingSamples": 1,
    "dealertingSamples": 3,
    "threshold": 50,
    "queryDefinition": {
      "type": "LOG",
      "logQuery": "log.source=\"fsxn\" AND content=\"Failure\"",
      "aggregation": "COUNT"
    }
  }
}' "Failed Access Spike"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Metric event creation complete"
echo ""
echo "View alerts: ${DT_ENV_URL}/ui/settings/builtin:anomaly-detection.metric-events"
echo ""
echo "Next steps:"
echo "  - Configure alerting profiles for notification routing"
echo "  - Add webhook integration to forward to SNS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
