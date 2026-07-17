#!/bin/bash
# Elastic — Create FSx for ONTAP Security Detection Rules via Kibana API
#
# Creates 3 detection rules using Elastic Security:
#   1. Ransomware Detection (ARP EMS event)
#   2. Mass File Deletion (>100 deletes in 5min from single user)
#   3. Failed Access Spike (>50 failures in 5min)
#
# Threshold customization:
#   Edit threshold values in the create_rule payloads below.
#   - Mass deletion: "value": 100 → adjust to your environment
#   - Failed access: "value": 50 → adjust to your environment
#
# Detection rationale:
#   See docs/en/detection-use-cases.md for why these 3 rules were chosen.
#
# Prerequisites:
#   - Kibana API access with Security write permissions
#   - Index: fsxn-audit-* with ECS-mapped fields
#
# Usage:
#   export KIBANA_URL="https://<cluster>.kb.<region>.aws.cloud.es.io:9243"
#   export ELASTIC_API_KEY="<your-api-key>"
#   bash integrations/elastic/scripts/create-alerts.sh

set -euo pipefail

KIBANA_URL="${KIBANA_URL:-}"
ELASTIC_API_KEY="${ELASTIC_API_KEY:-}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Elastic — Create FSx for ONTAP Security Rules"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -z "${KIBANA_URL}" ] || [ -z "${ELASTIC_API_KEY}" ]; then
  echo "❌ ERROR: KIBANA_URL and ELASTIC_API_KEY must be set."
  exit 1
fi

create_rule() {
  local payload="$1"
  local name="$2"

  echo "  Creating: ${name}..."

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${KIBANA_URL}/api/detection_engine/rules" \
    -H "kbn-xsrf: true" \
    -H "Content-Type: application/json" \
    -H "Authorization: ApiKey ${ELASTIC_API_KEY}" \
    -d "${payload}")

  if [ "${HTTP_CODE}" = "200" ]; then
    echo "    ✅ Created"
  elif [ "${HTTP_CODE}" = "409" ]; then
    echo "    ⚠️  Already exists (HTTP 409)"
  else
    echo "    ❌ Failed (HTTP ${HTTP_CODE})"
  fi
}

echo ""

# Rule 1: ARP Ransomware Detection
create_rule '{
  "rule_id": "fsxn-arp-ransomware-detection",
  "name": "FSx for ONTAP: Ransomware Activity Detected (ARP)",
  "description": "ONTAP ARP/AI detected ransomware-like activity (arw.volume.state EMS event). Investigate immediately.",
  "type": "query",
  "index": ["fsxn-audit-*"],
  "query": "event.action: \"arw.volume.state\" OR message: \"callhome.arw.activity.seen\"",
  "language": "kuery",
  "severity": "critical",
  "risk_score": 90,
  "interval": "5m",
  "from": "now-6m",
  "enabled": true,
  "tags": ["FSx for ONTAP", "Ransomware", "ARP"]
}' "Ransomware Detection (ARP)"

# Rule 2: Mass File Deletion
create_rule '{
  "rule_id": "fsxn-mass-file-deletion",
  "name": "FSx for ONTAP: Mass File Deletion (>100 in 5min)",
  "description": "A single user deleted more than 100 files in 5 minutes. Potential data destruction or ransomware cleanup phase.",
  "type": "threshold",
  "index": ["fsxn-audit-*"],
  "query": "event.action: \"Delete\" OR event.action: \"DeleteFile\"",
  "language": "kuery",
  "threshold": {"field": ["user.name"], "value": 100},
  "severity": "high",
  "risk_score": 75,
  "interval": "5m",
  "from": "now-6m",
  "enabled": true,
  "tags": ["FSx for ONTAP", "Data Destruction", "Mass Delete"]
}' "Mass File Deletion"

# Rule 3: Failed Access Spike
create_rule '{
  "rule_id": "fsxn-failed-access-spike",
  "name": "FSx for ONTAP: Failed Access Spike (>50 in 5min)",
  "description": "More than 50 failed access attempts in 5 minutes. Possible brute-force, permission misconfiguration, or unauthorized access attempt.",
  "type": "threshold",
  "index": ["fsxn-audit-*"],
  "query": "event.outcome: \"failure\"",
  "language": "kuery",
  "threshold": {"field": [], "value": 50},
  "severity": "medium",
  "risk_score": 50,
  "interval": "5m",
  "from": "now-6m",
  "enabled": true,
  "tags": ["FSx for ONTAP", "Access Control", "Brute Force"]
}' "Failed Access Spike"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Detection rule creation complete"
echo ""
echo "View rules: ${KIBANA_URL}/app/security/rules"
echo ""
echo "Next steps:"
echo "  - Configure rule actions (email, Slack, webhook to SNS)"
echo "  - Tune thresholds based on your environment baseline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
