#!/bin/bash
# Deploy FSx for ONTAP Forensic Investigation Dashboard via Grafana HTTP API
#
# This imports the forensics-investigation.json dashboard that provides
# DII Storage Workload Security equivalent views: user timeline, all activity,
# IP drill-down, file entity history.
#
# Prerequisites:
#   - Grafana Service Account token (glsa_ prefix) with Editor or Admin role
#   - Loki data source named "grafanacloud-logs" (or override with LOKI_DS_UID)
#
# Usage:
#   export GRAFANA_URL="https://your-instance.grafana.net"
#   export GRAFANA_SA_TOKEN="glsa_xxxx"
#   bash integrations/grafana/scripts/deploy-forensics-dashboard.sh
#
# To create a Service Account token:
#   Grafana UI → Administration → Service Accounts → Add → Add token

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_FILE="${SCRIPT_DIR}/../dashboards/forensics-investigation.json"

GRAFANA_URL="${GRAFANA_URL:-https://your-instance.grafana.net}"
GRAFANA_SA_TOKEN="${GRAFANA_SA_TOKEN:-}"
LOKI_DS_UID="${LOKI_DS_UID:-grafanacloud-logs}"

if [ -z "${GRAFANA_SA_TOKEN}" ]; then
  echo "ERROR: GRAFANA_SA_TOKEN is not set."
  echo ""
  echo "To create a Service Account token:"
  echo "  1. Go to ${GRAFANA_URL}/org/serviceaccounts"
  echo "  2. Click 'Add service account'"
  echo "  3. Name: 'forensics-deploy', Role: 'Editor'"
  echo "  4. Click 'Add service account token'"
  echo "  5. Copy the token (glsa_ prefix)"
  echo "  6. export GRAFANA_SA_TOKEN='glsa_...'"
  echo "  7. Re-run this script"
  exit 1
fi

if [ ! -f "${DASHBOARD_FILE}" ]; then
  echo "ERROR: Dashboard file not found: ${DASHBOARD_FILE}"
  exit 1
fi

echo "=== Deploying FSx for ONTAP Forensic Investigation Dashboard ==="
echo "Grafana URL: ${GRAFANA_URL}"
echo "Loki DS UID: ${LOKI_DS_UID}"
echo ""

# Read the dashboard JSON and wrap it in the Grafana API envelope
DASHBOARD_JSON=$(cat "${DASHBOARD_FILE}")

# Replace datasource UID if custom value provided
if [ "${LOKI_DS_UID}" != "grafanacloud-logs" ]; then
  echo "Overriding Loki datasource UID: ${LOKI_DS_UID}"
  DASHBOARD_JSON=$(echo "${DASHBOARD_JSON}" | sed "s/grafanacloud-logs/${LOKI_DS_UID}/g")
fi

PAYLOAD=$(python3 -c "
import json, sys
dashboard = json.loads('''${DASHBOARD_JSON}''')
# Ensure id is null for creation
dashboard['id'] = None
payload = {
    'dashboard': dashboard,
    'overwrite': True,
    'message': 'Deployed forensics-investigation dashboard via script'
}
print(json.dumps(payload))
" 2>/dev/null || echo "")

if [ -z "${PAYLOAD}" ]; then
  # Fallback: use jq if available, otherwise raw cat
  if command -v jq &> /dev/null; then
    PAYLOAD=$(jq -n --argjson dashboard "$(cat "${DASHBOARD_FILE}")" \
      '{dashboard: ($dashboard | .id = null), overwrite: true, message: "Deployed forensics-investigation dashboard via script"}')
  else
    echo "ERROR: python3 or jq required to construct API payload"
    exit 1
  fi
fi

# Deploy via API
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${GRAFANA_URL}/api/dashboards/db" \
  -H "Authorization: Bearer ${GRAFANA_SA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  DASHBOARD_URL=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "(parse error)")
  echo "✅ Dashboard deployed successfully"
  echo "   URL: ${GRAFANA_URL}${DASHBOARD_URL}"
  echo ""
  echo "Dashboard contains:"
  echo "  • User Activity Overview (LogQL timeseries by user)"
  echo "  • All Activity Stream (LogQL table with JSON parsing)"
  echo "  • IP Drill-Down (client_ip aggregation)"
  echo "  • File Entity History (path filter)"
  echo "  • ARP Alert Timeline (ransomware detection events)"
  echo ""
  echo "Template variables: \$user, \$client_ip, \$path, \$datasource"
else
  echo "❌ Failed to deploy dashboard (HTTP ${HTTP_CODE})"
  echo "Response: ${BODY}"
  echo ""
  echo "Common issues:"
  echo "  - 401: Token expired or invalid scope. Regenerate with Editor role."
  echo "  - 403: Service account lacks dashboard write permission."
  echo "  - 412: Dashboard with same UID exists and overwrite=false."
  exit 1
fi
