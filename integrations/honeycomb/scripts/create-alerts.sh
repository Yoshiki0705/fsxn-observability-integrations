#!/bin/bash
# Honeycomb — Create FSx for ONTAP Triggers (Alerts)
#
# Creates 3 triggers:
#   1. Ransomware Detection (ARP event)
#   2. Mass File Deletion (>100 deletes in 5min)
#   3. Failed Access Spike (>50 failures in 5min)
#
# Threshold customization:
#   Edit the "value" fields in threshold objects below.
#   Detection rationale: docs/en/detection-use-cases.md
#
# Prerequisites:
#   - Honeycomb API Key (Configuration key, not Ingest key)
#   - Dataset: fsxn-audit
#
# Usage:
#   export HONEYCOMB_API_KEY="<configuration-api-key>"
#   export HONEYCOMB_DATASET="fsxn-audit"
#   bash integrations/honeycomb/scripts/create-alerts.sh

set -euo pipefail

HONEYCOMB_API_KEY="${HONEYCOMB_API_KEY:-}"
HONEYCOMB_DATASET="${HONEYCOMB_DATASET:-fsxn-audit}"
HONEYCOMB_API="${HONEYCOMB_API:-https://api.honeycomb.io}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Honeycomb — Create FSx for ONTAP Triggers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${HONEYCOMB_API_KEY}" ]; then
  echo "❌ ERROR: HONEYCOMB_API_KEY must be set."
  echo "  Use a Configuration key (not Ingest key)."
  exit 1
fi

create_trigger() {
  local payload="$1"
  local name="$2"

  echo "  Creating: ${name}..."

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${HONEYCOMB_API}/1/triggers/${HONEYCOMB_DATASET}" \
    -H "Content-Type: application/json" \
    -H "X-Honeycomb-Team: ${HONEYCOMB_API_KEY}" \
    -d "${payload}")

  if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "201" ]; then
    echo "    ✅ Created"
  else
    echo "    ❌ Failed (HTTP ${HTTP_CODE})"
  fi
}

echo ""

create_trigger '{
  "name": "FSxN: Ransomware Detection (ARP)",
  "description": "ONTAP ARP/AI detected ransomware-like activity",
  "disabled": false,
  "query": {
    "calculations": [{"op": "COUNT"}],
    "filters": [{"column": "message_name", "op": "contains", "value": "arw"}],
    "time_range": 300,
    "breakdowns": []
  },
  "frequency": 300,
  "threshold": {"op": ">", "value": 0}
}' "Ransomware Detection (ARP)"

create_trigger '{
  "name": "FSxN: Mass File Deletion (>100 in 5min)",
  "description": "A single user deleted more than 100 files in 5 minutes",
  "disabled": false,
  "query": {
    "calculations": [{"op": "COUNT"}],
    "filters": [{"column": "operation", "op": "=", "value": "Delete"}],
    "time_range": 300,
    "breakdowns": ["user"]
  },
  "frequency": 300,
  "threshold": {"op": ">", "value": 100}
}' "Mass File Deletion"

create_trigger '{
  "name": "FSxN: Failed Access Spike (>50 in 5min)",
  "description": "More than 50 failed access attempts in 5 minutes",
  "disabled": false,
  "query": {
    "calculations": [{"op": "COUNT"}],
    "filters": [{"column": "result", "op": "=", "value": "Failure"}],
    "time_range": 300,
    "breakdowns": []
  },
  "frequency": 300,
  "threshold": {"op": ">", "value": 50}
}' "Failed Access Spike"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Trigger creation complete"
echo ""
echo "View triggers: https://ui.honeycomb.io/triggers"
echo ""
echo "Next steps:"
echo "  - Add recipients to triggers (Slack, PagerDuty, webhook)"
echo "  - Connect webhook to SNS for automated response"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

create_trigger() {
  local payload="$1"
  local name="$2"

  echo "  Creating: ${name}..."

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${HONEYCOMB_API}/1/triggers/${HONEYCOMB_DATASET}" \
    -H "Content-Type: application/json" \
    -H "X-Honeycomb-Team: ${HONEYCOMB_API_KEY}" \
    -d "${payload}")

  if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "201" ]; then
    echo "    ✅ Created"
  else
    echo "    ❌ Failed (HTTP ${HTTP_CODE})"
  fi
}

create_trigger '{
  "name": "FSxN: Ransomware Detection (ARP)",
  "description": "ONTAP ARP/AI detected ransomware-like activity",
  "disabled": false,
  "query": {
    "calculations": [{"op": "COUNT"}],
    "filters": [{"column": "message_name", "op": "contains", "value": "arw"}],
    "time_range": 300
  },
  "frequency": 300,
  "threshold": {"op": ">", "value": 0}
}' "Ransomware Detection (ARP)"

create_trigger '{
  "name": "FSxN: Mass File Deletion (>100 in 5min)",
  "description": "A user deleted more than 100 files in 5 minutes",
  "disabled": false,
  "query": {
    "calculations": [{"op": "COUNT"}],
    "filters": [{"column": "operation", "op": "=", "value": "Delete"}],
    "time_range": 300,
    "breakdowns": ["user"]
  },
  "frequency": 300,
  "threshold": {"op": ">", "value": 100}
}' "Mass File Deletion"

create_trigger '{
  "name": "FSxN: Failed Access Spike (>50 in 5min)",
  "description": "More than 50 failed access attempts in 5 minutes",
  "disabled": false,
  "query": {
    "calculations": [{"op": "COUNT"}],
    "filters": [{"column": "result", "op": "=", "value": "Failure"}],
    "time_range": 300
  },
  "frequency": 300,
  "threshold": {"op": ">", "value": 50}
}' "Failed Access Spike"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Trigger creation complete"
echo ""
echo "View triggers: https://ui.honeycomb.io/triggers"
echo ""
echo "Next steps:"
echo "  - Add recipients (Slack, PagerDuty, webhook)"
echo "  - Connect webhook to SNS for automated response"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
