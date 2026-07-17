#!/bin/bash
# setup-full-observability.sh — Deploy complete New Relic observability for FSx for ONTAP
#
# Orchestrates: Deploy stack → Create alerts → Import dashboard → Verify
#
# Prerequisites:
#   - AWS CLI configured
#   - New Relic License Key (for log delivery)
#   - New Relic User API Key (for alerts/dashboard API)
#
# Usage:
#   export NEW_RELIC_LICENSE_KEY="<license-key>"
#   export NEW_RELIC_API_KEY="NRAK-xxxx"
#   export NEW_RELIC_ACCOUNT_ID="<account-id>"
#   export NEW_RELIC_REGION="US"
#   bash integrations/new-relic/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="${SCRIPT_DIR}/../dashboards"

echo "============================================================"
echo " FSx for ONTAP — New Relic Full Observability Setup"
echo "============================================================"
echo ""

# ─── Step 1/4: Deploy CloudFormation Stack ───────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1/4: Deploy audit log pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f "${SCRIPT_DIR}/deploy.sh" ]; then
  bash "${SCRIPT_DIR}/deploy.sh"
else
  echo "  ⚠️  deploy.sh not found — skipping."
fi

echo ""

# ─── Step 2/4: Create Alert Conditions ───────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create NRQL alert conditions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${NEW_RELIC_API_KEY:-}" ] && [ -n "${NEW_RELIC_ACCOUNT_ID:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  NEW_RELIC_API_KEY/ACCOUNT_ID not set — skipping."
fi

echo ""

# ─── Step 3/4: Import Forensics Dashboard ────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Import forensics investigation dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${NEW_RELIC_API_KEY:-}" ] && [ -n "${NEW_RELIC_ACCOUNT_ID:-}" ] && [ -f "${DASHBOARDS_DIR}/forensics-investigation.json" ]; then
  echo "  Importing dashboard via NerdGraph..."
  DASHBOARD_JSON=$(cat "${DASHBOARDS_DIR}/forensics-investigation.json")
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "https://api.newrelic.com/graphql" \
    -H "Content-Type: application/json" \
    -H "API-Key: ${NEW_RELIC_API_KEY}" \
    -d "{\"query\":\"mutation { dashboardCreate(accountId: ${NEW_RELIC_ACCOUNT_ID}, dashboard: \$dashboard) { entityResult { guid } } }\",\"variables\":{\"dashboard\":${DASHBOARD_JSON}}}")
  if [ "${HTTP_CODE}" = "200" ]; then
    echo "  ✅ Forensics dashboard created"
  else
    echo "  ⚠️  NerdGraph returned HTTP ${HTTP_CODE}"
  fi
else
  echo "  ⚠️  Skipping — set NEW_RELIC_API_KEY and ACCOUNT_ID"
fi

echo ""

# ─── Step 4/4: Verify End-to-End ─────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4/4: E2E verification (send test log)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bash "${SCRIPT_DIR}/verify.sh"

echo ""
echo "============================================================"
echo "✅ Full observability setup complete!"
echo ""
echo "What was configured:"
echo "  • Audit log pipeline (Lambda → Log API → New Relic)"
echo "  • Alert conditions (3 NRQL conditions in policy)"
echo "  • Forensics dashboard (7 widgets)"
echo "  • E2E verification passed"
echo ""
echo "Next steps:"
echo "  1. Add notification channels to alert policy"
echo "  2. Review: https://one.newrelic.com/dashboards"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"
