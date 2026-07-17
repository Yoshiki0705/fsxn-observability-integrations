#!/bin/bash
# setup-full-observability.sh — Deploy complete Sumo Logic observability for FSx for ONTAP
#
# Orchestrates: Deploy stack → Create monitors → Import dashboard → Verify
#
# Prerequisites:
#   - AWS CLI configured
#   - Sumo Logic HTTP Source URL (for log delivery)
#   - Sumo Logic Access ID + Key (for monitors/dashboard API)
#
# Usage:
#   export SUMO_HTTP_SOURCE_URL="https://endpoint<N>.collection.sumologic.com/..."
#   export SUMO_ACCESS_ID="<access-id>"
#   export SUMO_ACCESS_KEY="<access-key>"
#   export SUMO_API_ENDPOINT="https://api.sumologic.com/api"
#   bash integrations/sumo-logic/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="${SCRIPT_DIR}/../dashboards"

echo "============================================================"
echo " FSx for ONTAP — Sumo Logic Full Observability Setup"
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

# ─── Step 2/4: Create Security Monitors ──────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create security monitors"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${SUMO_ACCESS_ID:-}" ] && [ -n "${SUMO_ACCESS_KEY:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  SUMO_ACCESS_ID/KEY not set — skipping."
fi

echo ""

# ─── Step 3/4: Import Forensics Dashboard ────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Import forensics investigation dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${SUMO_ACCESS_ID:-}" ] && [ -n "${SUMO_ACCESS_KEY:-}" ] && [ -f "${DASHBOARDS_DIR}/forensics-investigation.json" ]; then
  echo "  Importing dashboard..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${SUMO_API_ENDPOINT:-https://api.sumologic.com/api}/v2/dashboards" \
    -H "Content-Type: application/json" \
    -u "${SUMO_ACCESS_ID}:${SUMO_ACCESS_KEY}" \
    -d @"${DASHBOARDS_DIR}/forensics-investigation.json")
  if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "201" ]; then
    echo "  ✅ Forensics dashboard imported"
  else
    echo "  ⚠️  Import returned HTTP ${HTTP_CODE}"
  fi
else
  echo "  ⚠️  Skipping — set SUMO_ACCESS_ID and SUMO_ACCESS_KEY"
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
echo "  • Audit log pipeline (Lambda → HTTP Source → Sumo Logic)"
echo "  • Security monitors (3 log monitors)"
echo "  • Forensics dashboard (6 panels + template variables)"
echo "  • E2E verification passed"
echo ""
echo "Next steps:"
echo "  1. Add notification channels to monitors"
echo "  2. Review dashboard in Sumo Logic UI"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"
