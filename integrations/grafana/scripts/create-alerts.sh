#!/bin/bash
# Provision FSx for ONTAP Alerting Rules via Grafana HTTP API
#
# Creates a "FSx for ONTAP Alerts" folder and provisions three alert rules:
#   1. Ransomware Detection (ARP volume state change)
#   2. Quota Warning (WAFL soft limit exceeded)
#   3. Failed Access Spike (>10 failures in 5 minutes)
#
# Prerequisites:
#   - Grafana Service Account token (glsa_ prefix) with Editor or Admin role
#   - Logs flowing to Grafana Cloud via OTLP Gateway
#   - Loki datasource UID: grafanacloud-logs
#
# Usage:
#   export GRAFANA_SA_TOKEN="glsa_xxxx"
#   export GRAFANA_URL="https://your-instance.grafana.net"
#   bash integrations/grafana/scripts/create-alerts.sh
#
# Reference:
#   https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/

set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-https://your-instance.grafana.net}"
GRAFANA_SA_TOKEN="${GRAFANA_SA_TOKEN:-}"
LOKI_DATASOURCE_UID="${LOKI_DATASOURCE_UID:-grafanacloud-logs}"

if [ -z "${GRAFANA_SA_TOKEN}" ]; then
  echo "ERROR: GRAFANA_SA_TOKEN is not set."
  echo ""
  echo "To create a Service Account token:"
  echo "  1. Go to ${GRAFANA_URL}/org/serviceaccounts"
  echo "  2. Click 'Add service account'"
  echo "  3. Name: 'alerting-provisioner', Role: 'Editor'"
  echo "  4. Click 'Add service account token'"
  echo "  5. Copy the token (glsa_ prefix)"
  echo "  6. export GRAFANA_SA_TOKEN='glsa_...'"
  echo "  7. Re-run this script"
  exit 1
fi

echo "=== Provisioning FSx for ONTAP Alert Rules ==="
echo "Grafana URL: ${GRAFANA_URL}"
echo "Datasource UID: ${LOKI_DATASOURCE_UID}"
echo ""

# --- Step 1: Create or find the "FSx for ONTAP Alerts" folder ---
echo "Step 1: Creating alert folder 'FSx for ONTAP Alerts'..."

FOLDER_PAYLOAD=$(cat << 'EOF'
{
  "uid": "fsxn-alerts",
  "title": "FSx for ONTAP Alerts"
}
EOF
)

FOLDER_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${GRAFANA_URL}/api/folders" \
  -H "Authorization: Bearer ${GRAFANA_SA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${FOLDER_PAYLOAD}")

FOLDER_HTTP=$(echo "$FOLDER_RESPONSE" | tail -1)
FOLDER_BODY=$(echo "$FOLDER_RESPONSE" | sed '$d')

if [ "$FOLDER_HTTP" = "200" ] || [ "$FOLDER_HTTP" = "412" ]; then
  echo "  Folder ready (HTTP ${FOLDER_HTTP})"
  FOLDER_UID="fsxn-alerts"
else
  echo "  WARNING: Folder creation returned HTTP ${FOLDER_HTTP}"
  echo "  Response: ${FOLDER_BODY}"
  echo "  Attempting to continue with folder UID 'fsxn-alerts'..."
  FOLDER_UID="fsxn-alerts"
fi

# --- Step 2: Provision alert rules via the provisioning API ---
echo ""
echo "Step 2: Provisioning alert rules..."

# Build the alert rule group payload
RULES_PAYLOAD=$(cat << EOF
{
  "name": "FSx for ONTAP Security Alerts",
  "interval": "1m",
  "rules": [
    {
      "uid": "fsxn-ransomware-detection",
      "title": "FSx for ONTAP: Ransomware Activity Detected (ARP)",
      "condition": "C",
      "data": [
        {
          "refId": "A",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "${LOKI_DATASOURCE_UID}",
          "model": {
            "expr": "count_over_time({service_name=\"fsxn-ems\"} | json | event_name=\"arw.volume.state\" [5m])",
            "queryType": "range",
            "refId": "A"
          }
        },
        {
          "refId": "B",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "__expr__",
          "model": {
            "type": "reduce",
            "expression": "A",
            "reducer": "last",
            "refId": "B"
          }
        },
        {
          "refId": "C",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "__expr__",
          "model": {
            "type": "threshold",
            "expression": "B",
            "conditions": [{"evaluator": {"type": "gt", "params": [0]}}],
            "refId": "C"
          }
        }
      ],
      "noDataState": "OK",
      "execErrState": "Error",
      "for": "0s",
      "annotations": {
        "summary": "ONTAP Anti-Ransomware Protection detected a volume state change",
        "description": "The arw.volume.state EMS event indicates potential ransomware activity on an FSx for ONTAP volume. Investigate immediately.",
        "runbook_url": "https://docs.netapp.com/us-en/ontap/anti-ransomware/respond-abnormal-task.html"
      },
      "labels": {
        "severity": "critical",
        "team": "storage",
        "source": "fsxn-ems"
      }
    },
    {
      "uid": "fsxn-quota-warning",
      "title": "FSx for ONTAP: Storage Quota Soft Limit Exceeded",
      "condition": "C",
      "data": [
        {
          "refId": "A",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "${LOKI_DATASOURCE_UID}",
          "model": {
            "expr": "count_over_time({service_name=\"fsxn-ems\"} | json | event_name=\"wafl.quota.softlimit.exceeded\" [5m])",
            "queryType": "range",
            "refId": "A"
          }
        },
        {
          "refId": "B",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "__expr__",
          "model": {
            "type": "reduce",
            "expression": "A",
            "reducer": "last",
            "refId": "B"
          }
        },
        {
          "refId": "C",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "__expr__",
          "model": {
            "type": "threshold",
            "expression": "B",
            "conditions": [{"evaluator": {"type": "gt", "params": [0]}}],
            "refId": "C"
          }
        }
      ],
      "noDataState": "OK",
      "execErrState": "Error",
      "for": "0s",
      "annotations": {
        "summary": "WAFL quota soft limit exceeded on FSx for ONTAP",
        "description": "A user or qtree has exceeded their storage quota soft limit. Review quota usage and consider increasing limits or notifying the user."
      },
      "labels": {
        "severity": "warning",
        "team": "storage",
        "source": "fsxn-ems"
      }
    },
    {
      "uid": "fsxn-failed-access-spike",
      "title": "FSx for ONTAP: Failed Access Spike (>10 in 5min)",
      "condition": "C",
      "data": [
        {
          "refId": "A",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "${LOKI_DATASOURCE_UID}",
          "model": {
            "expr": "count_over_time({service_name=\"fsxn-audit\"} | json | Result=\"Failure\" [5m])",
            "queryType": "range",
            "refId": "A"
          }
        },
        {
          "refId": "B",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "__expr__",
          "model": {
            "type": "reduce",
            "expression": "A",
            "reducer": "last",
            "refId": "B"
          }
        },
        {
          "refId": "C",
          "relativeTimeRange": {"from": 300, "to": 0},
          "datasourceUid": "__expr__",
          "model": {
            "type": "threshold",
            "expression": "B",
            "conditions": [{"evaluator": {"type": "gt", "params": [10]}}],
            "refId": "C"
          }
        }
      ],
      "noDataState": "OK",
      "execErrState": "Error",
      "for": "0s",
      "annotations": {
        "summary": "High rate of failed access attempts on FSx for ONTAP",
        "description": "More than 10 failed access attempts detected in the last 5 minutes. This may indicate brute-force attempts, permission misconfiguration, or unauthorized access."
      },
      "labels": {
        "severity": "warning",
        "team": "security",
        "source": "fsxn-audit"
      }
    }
  ]
}
EOF
)

RULES_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X PUT "${GRAFANA_URL}/api/v1/provisioning/folder/${FOLDER_UID}/rule-groups/FSx for ONTAP%20Security%20Alerts" \
  -H "Authorization: Bearer ${GRAFANA_SA_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Disable-Provenance: true" \
  -d "${RULES_PAYLOAD}")

RULES_HTTP=$(echo "$RULES_RESPONSE" | tail -1)
RULES_BODY=$(echo "$RULES_RESPONSE" | sed '$d')

echo ""
if [ "$RULES_HTTP" = "200" ] || [ "$RULES_HTTP" = "201" ] || [ "$RULES_HTTP" = "202" ]; then
  echo "=== Alert Rules Provisioned Successfully ==="
  echo ""
  echo "Rules created in folder 'FSx for ONTAP Alerts':"
  echo "  1. FSx for ONTAP: Ransomware Activity Detected (ARP)  [severity: critical]"
  echo "     Query: {service_name=\"fsxn-ems\"} | json | event_name=\"arw.volume.state\""
  echo ""
  echo "  2. FSx for ONTAP: Storage Quota Soft Limit Exceeded    [severity: warning]"
  echo "     Query: {service_name=\"fsxn-ems\"} | json | event_name=\"wafl.quota.softlimit.exceeded\""
  echo ""
  echo "  3. FSx for ONTAP: Failed Access Spike (>10 in 5min)   [severity: warning]"
  echo "     Query: {service_name=\"fsxn-audit\"} | json | Result=\"Failure\""
  echo ""
  echo "View alerts: ${GRAFANA_URL}/alerting/list"
  echo ""
  echo "Next steps:"
  echo "  - Configure contact points (email, Slack, PagerDuty) in Grafana UI"
  echo "  - Create notification policies to route alerts by severity/team label"
else
  echo "ERROR: Failed to provision alert rules (HTTP ${RULES_HTTP})"
  echo "Response: ${RULES_BODY}"
  echo ""
  echo "Common issues:"
  echo "  - Token needs Editor or Admin role"
  echo "  - Datasource UID '${LOKI_DATASOURCE_UID}' may not exist"
  echo "  - Unified alerting may not be enabled"
  exit 1
fi
