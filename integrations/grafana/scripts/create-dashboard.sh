#!/bin/bash
# Create FSx for ONTAP Audit Log Dashboard via Grafana HTTP API
#
# Prerequisites:
#   - Grafana Service Account token (glsa_ prefix) with Editor or Admin role
#   - OR: Set GRAFANA_SA_TOKEN environment variable
#
# Usage:
#   export GRAFANA_SA_TOKEN="glsa_xxxx"
#   bash integrations/grafana/scripts/create-dashboard.sh
#
# Note: The glc_ token (Cloud Stack token) does NOT work for the Grafana HTTP API.
#       You need a Service Account token created via:
#       Grafana UI -> Administration -> Service Accounts -> Add service account -> Add token

set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-https://your-instance.grafana.net}"
GRAFANA_SA_TOKEN="${GRAFANA_SA_TOKEN:-}"

if [ -z "${GRAFANA_SA_TOKEN}" ]; then
  echo "ERROR: GRAFANA_SA_TOKEN is not set."
  echo ""
  echo "To create a Service Account token:"
  echo "  1. Go to ${GRAFANA_URL}/org/serviceaccounts"
  echo "  2. Click 'Add service account'"
  echo "  3. Name: 'e2e-verification', Role: 'Editor'"
  echo "  4. Click 'Add service account token'"
  echo "  5. Copy the token (glsa_ prefix)"
  echo "  6. export GRAFANA_SA_TOKEN='glsa_...'"
  echo "  7. Re-run this script"
  exit 1
fi

echo "=== Creating FSx for ONTAP Audit Log Dashboard ==="
echo "Grafana URL: ${GRAFANA_URL}"

# Create dashboard JSON payload
PAYLOAD=$(cat << 'EOF'
{
  "dashboard": {
    "id": null,
    "uid": "fsxn-audit-overview",
    "title": "FSx for ONTAP Audit Log Dashboard",
    "tags": ["fsxn", "audit", "ontap", "e2e-verification"],
    "timezone": "browser",
    "schemaVersion": 39,
    "refresh": "30s",
    "panels": [
      {
        "id": 1,
        "title": "Log Volume",
        "type": "timeseries",
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
        "datasource": { "type": "loki", "uid": "grafanacloud-logs" },
        "targets": [
          {
            "expr": "count_over_time({service_name=\"fsxn-audit\"}[5m])",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": { "mode": "palette-classic" },
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 20,
              "gradientMode": "scheme"
            }
          },
          "overrides": []
        },
        "options": {
          "tooltip": { "mode": "multi" },
          "legend": { "displayMode": "list", "placement": "bottom" }
        }
      },
      {
        "id": 2,
        "title": "Operations Breakdown",
        "type": "piechart",
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
        "datasource": { "type": "loki", "uid": "grafanacloud-logs" },
        "targets": [
          {
            "expr": "sum by (Operation) (count_over_time({service_name=\"fsxn-audit\"} | json [1h]))",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": { "mode": "palette-classic" }
          },
          "overrides": []
        },
        "options": {
          "legend": { "displayMode": "list", "placement": "right" },
          "pieType": "pie",
          "tooltip": { "mode": "single" }
        }
      },
      {
        "id": 3,
        "title": "User Activity Top 10",
        "type": "bargauge",
        "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
        "datasource": { "type": "loki", "uid": "grafanacloud-logs" },
        "targets": [
          {
            "expr": "topk(10, sum by (UserName) (count_over_time({service_name=\"fsxn-audit\"} | json [1h])))",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": { "mode": "palette-classic" },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "color": "green", "value": null },
                { "color": "yellow", "value": 50 },
                { "color": "red", "value": 100 }
              ]
            }
          },
          "overrides": []
        },
        "options": {
          "orientation": "horizontal",
          "displayMode": "gradient",
          "reduceOptions": { "calcs": ["lastNotNull"] }
        }
      },
      {
        "id": 4,
        "title": "Failed Events",
        "type": "timeseries",
        "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
        "datasource": { "type": "loki", "uid": "grafanacloud-logs" },
        "targets": [
          {
            "expr": "count_over_time({service_name=\"fsxn-audit\"} | json | Result=\"Failure\" [5m])",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": { "mode": "fixed", "fixedColor": "red" },
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 30,
              "gradientMode": "scheme"
            }
          },
          "overrides": []
        },
        "options": {
          "tooltip": { "mode": "multi" },
          "legend": { "displayMode": "list", "placement": "bottom" }
        }
      }
    ],
    "time": { "from": "now-1h", "to": "now" }
  },
  "overwrite": true,
  "message": "Created by E2E verification script"
}
EOF
)

# Create dashboard via API
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${GRAFANA_URL}/api/dashboards/db" \
  -H "Authorization: Bearer ${GRAFANA_SA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP Status: ${HTTP_CODE}"

if [ "$HTTP_CODE" = "200" ]; then
  DASHBOARD_URL=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "")
  DASHBOARD_UID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('uid',''))" 2>/dev/null || echo "")
  echo ""
  echo "=== Dashboard Created Successfully ==="
  echo "Dashboard URL: ${GRAFANA_URL}${DASHBOARD_URL}"
  echo "Dashboard UID: ${DASHBOARD_UID}"
  echo ""
  echo "Panels:"
  echo "  1. Log Volume (Time series) - count_over_time({service_name=\"fsxn-audit\"}[5m])"
  echo "  2. Operations Breakdown (Pie chart) - sum by (Operation)"
  echo "  3. User Activity Top 10 (Bar gauge) - topk(10, sum by (UserName))"
  echo "  4. Failed Events (Time series) - Result=\"Failure\""
else
  echo "ERROR: Failed to create dashboard"
  echo "Response: ${BODY}"
  exit 1
fi
