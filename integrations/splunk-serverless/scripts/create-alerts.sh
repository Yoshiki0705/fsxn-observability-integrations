#!/bin/bash
# Splunk — Create FSx for ONTAP Security Alerts via REST API
#
# Creates 3 saved searches with alert actions:
#   1. Ransomware Detection (ARP EMS event)
#   2. Mass File Deletion (>100 deletes in 5min from single user)
#   3. Failed Access Spike (>50 failures in 5min)
#
# Prerequisites:
#   - Splunk admin credentials or token with saved search write access
#   - Index: fsxn_audit populated with FSx for ONTAP audit logs
#
# Usage:
#   export SPLUNK_URL="https://<host>:8089"
#   export SPLUNK_TOKEN="<bearer-token>"  # or use SPLUNK_USER + SPLUNK_PASS
#   bash integrations/splunk-serverless/scripts/create-alerts.sh

set -euo pipefail

SPLUNK_URL="${SPLUNK_URL:-}"
SPLUNK_TOKEN="${SPLUNK_TOKEN:-}"
SPLUNK_USER="${SPLUNK_USER:-admin}"
SPLUNK_PASS="${SPLUNK_PASS:-}"
SPLUNK_INDEX="${SPLUNK_INDEX:-fsxn_audit}"
SPLUNK_APP="${SPLUNK_APP:-search}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Splunk — Create FSx for ONTAP Security Alerts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${SPLUNK_URL}" ]; then
  echo "❌ ERROR: SPLUNK_URL must be set."
  echo "  export SPLUNK_URL='https://<host>:8089'"
  exit 1
fi

# Build auth header
if [ -n "${SPLUNK_TOKEN}" ]; then
  AUTH_HEADER="Authorization: Bearer ${SPLUNK_TOKEN}"
elif [ -n "${SPLUNK_PASS}" ]; then
  AUTH_HEADER="Authorization: Basic $(echo -n "${SPLUNK_USER}:${SPLUNK_PASS}" | base64)"
else
  echo "❌ ERROR: Set SPLUNK_TOKEN or SPLUNK_PASS"
  exit 1
fi

create_alert() {
  local name="$1"
  local search="$2"
  local severity="$3"
  local description="$4"

  echo "  Creating: ${name}..."

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -k \
    -X POST "${SPLUNK_URL}/servicesNS/${SPLUNK_USER}/${SPLUNK_APP}/saved/searches" \
    -H "${AUTH_HEADER}" \
    -d "name=${name}" \
    -d "search=${search}" \
    -d "is_scheduled=1" \
    -d "cron_schedule=*/5 * * * *" \
    -d "dispatch.earliest_time=-5m@m" \
    -d "dispatch.latest_time=now" \
    -d "alert_type=number of events" \
    -d "alert_comparator=greater than" \
    -d "alert_threshold=0" \
    -d "alert.severity=${severity}" \
    -d "alert.suppress=1" \
    -d "alert.suppress.period=15m" \
    -d "description=${description}" \
    -d "actions=email" \
    -d "alert.track=1")

  if [ "${HTTP_CODE}" = "201" ]; then
    echo "    ✅ Created"
  elif [ "${HTTP_CODE}" = "409" ]; then
    echo "    ⚠️  Already exists (HTTP 409)"
  else
    echo "    ❌ Failed (HTTP ${HTTP_CODE})"
  fi
}

echo ""
create_alert \
  "FSxN: Ransomware Detection (ARP)" \
  "index=${SPLUNK_INDEX} (message_name=\"callhome.arw.activity.seen\" OR message_name=\"arw.volume.state\") | stats count" \
  "5" \
  "ONTAP ARP/AI detected ransomware-like activity. Investigate immediately."

create_alert \
  "FSxN: Mass File Deletion (>100 in 5min)" \
  "index=${SPLUNK_INDEX} operation=Delete | stats count by user | where count > 100" \
  "4" \
  "A single user deleted more than 100 files in 5 minutes. Potential data destruction."

create_alert \
  "FSxN: Failed Access Spike (>50 in 5min)" \
  "index=${SPLUNK_INDEX} result=Failure | stats count | where count > 50" \
  "3" \
  "More than 50 failed access attempts in 5 minutes. Possible brute-force or misconfiguration."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Alert creation complete"
echo ""
echo "View alerts: ${SPLUNK_URL}/en-US/app/${SPLUNK_APP}/saved/searches"
echo ""
echo "Next steps:"
echo "  - Configure email recipients in Splunk alert actions"
echo "  - Or add webhook action to forward to SNS for automated response"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
