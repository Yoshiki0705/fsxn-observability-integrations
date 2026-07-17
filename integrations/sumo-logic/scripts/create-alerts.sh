#!/bin/bash
# Sumo Logic — Create FSx for ONTAP Security Monitors
#
# Creates 3 log monitors:
#   1. Ransomware Detection (ARP EMS event)
#   2. Mass File Deletion (>100 deletes in 5min from single user)
#   3. Failed Access Spike (>50 failures in 5min)
#
# Prerequisites:
#   - Sumo Logic Access ID + Key with Manage Monitors permission
#   - Logs flowing with _sourceCategory=fsxn*
#
# Usage:
#   export SUMO_ACCESS_ID="<your-access-id>"
#   export SUMO_ACCESS_KEY="<your-access-key>"
#   export SUMO_API_ENDPOINT="https://api.sumologic.com/api"
#   bash integrations/sumo-logic/scripts/create-alerts.sh

set -euo pipefail

SUMO_ACCESS_ID="${SUMO_ACCESS_ID:-}"
SUMO_ACCESS_KEY="${SUMO_ACCESS_KEY:-}"
SUMO_API_ENDPOINT="${SUMO_API_ENDPOINT:-https://api.sumologic.com/api}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Sumo Logic — Create FSx for ONTAP Security Monitors"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${SUMO_ACCESS_ID}" ] || [ -z "${SUMO_ACCESS_KEY}" ]; then
  echo "❌ ERROR: SUMO_ACCESS_ID and SUMO_ACCESS_KEY must be set."
  exit 1
fi

create_monitor() {
  local payload="$1"
  local name="$2"

  echo "  Creating: ${name}..."

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${SUMO_API_ENDPOINT}/v1/monitors" \
    -H "Content-Type: application/json" \
    -u "${SUMO_ACCESS_ID}:${SUMO_ACCESS_KEY}" \
    -d "${payload}")

  if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "201" ]; then
    echo "    ✅ Created"
  elif [ "${HTTP_CODE}" = "409" ]; then
    echo "    ⚠️  Already exists"
  else
    echo "    ❌ Failed (HTTP ${HTTP_CODE})"
  fi
}

echo ""

create_monitor '{
  "name": "FSxN: Ransomware Detection (ARP)",
  "description": "ONTAP ARP/AI detected ransomware-like activity. Investigate immediately.",
  "type": "MonitorsLibraryMonitor",
  "monitorType": "Logs",
  "queries": [{"rowId": "A", "query": "_sourceCategory=fsxn* | json field=_raw \"message_name\" | where message_name matches \"*arw*\" | count"}],
  "triggers": [{"triggerType": "Critical", "threshold": 0, "thresholdType": "GreaterThan", "occurrenceType": "ResultCount", "triggerSource": "AllResults", "detectionMethod": "StaticCondition"}],
  "isDisabled": false
}' "Ransomware Detection (ARP)"

create_monitor '{
  "name": "FSxN: Mass File Deletion (>100 in 5min)",
  "description": "A single user deleted more than 100 files in 5 minutes.",
  "type": "MonitorsLibraryMonitor",
  "monitorType": "Logs",
  "queries": [{"rowId": "A", "query": "_sourceCategory=fsxn* | json field=_raw \"user\", \"operation\" | where operation = \"Delete\" | count by user | where _count > 100"}],
  "triggers": [{"triggerType": "Critical", "threshold": 0, "thresholdType": "GreaterThan", "occurrenceType": "ResultCount", "triggerSource": "AllResults", "detectionMethod": "StaticCondition"}],
  "isDisabled": false
}' "Mass File Deletion"

create_monitor '{
  "name": "FSxN: Failed Access Spike (>50 in 5min)",
  "description": "More than 50 failed access attempts in 5 minutes.",
  "type": "MonitorsLibraryMonitor",
  "monitorType": "Logs",
  "queries": [{"rowId": "A", "query": "_sourceCategory=fsxn* | json field=_raw \"result\" | where result = \"Failure\" | count | where _count > 50"}],
  "triggers": [{"triggerType": "Warning", "threshold": 0, "thresholdType": "GreaterThan", "occurrenceType": "ResultCount", "triggerSource": "AllResults", "detectionMethod": "StaticCondition"}],
  "isDisabled": false
}' "Failed Access Spike"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Monitor creation complete"
echo ""
echo "View monitors: Sumo Logic → Manage Data → Monitoring → Monitors"
echo ""
echo "Next steps:"
echo "  - Add notification channels (email, Slack, PagerDuty, webhook)"
echo "  - Connect webhook to SNS for automated response pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
