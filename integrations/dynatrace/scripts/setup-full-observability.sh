#!/bin/bash
# setup-full-observability.sh — Deploy complete Dynatrace observability
#
# Orchestrates: Deploy → Alerts → Dashboard → Verify
#
# Usage:
#   export DT_ENV_URL="https://<env-id>.live.dynatrace.com"
#   export DT_API_TOKEN="<token>"
#   bash integrations/dynatrace/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="${SCRIPT_DIR}/../dashboards"

echo "============================================================"
echo " FSx for ONTAP — Dynatrace Full Observability Setup"
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

# ─── Step 2/4: Create Metric Events (Alerts) ─────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create log metric event alerts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${DT_ENV_URL:-}" ] && [ -n "${DT_API_TOKEN:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  DT_ENV_URL/DT_API_TOKEN not set — skipping."
fi

echo ""

# ─── Step 3/4: Import Forensics Dashboard ────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Import forensics investigation dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${DT_ENV_URL:-}" ] && [ -n "${DT_API_TOKEN:-}" ] && [ -f "${DASHBOARDS_DIR}/forensics-investigation.json" ]; then
  echo "  Importing dashboard..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${DT_ENV_URL}/api/config/v1/dashboards" \
    -H "Content-Type: application/json" \
    -H "Authorization: Api-Token ${DT_API_TOKEN}" \
    -d @"${DASHBOARDS_DIR}/forensics-investigation.json")
  if [ "${HTTP_CODE}" = "201" ]; then
    echo "  ✅ Forensics dashboard created"
  else
    echo "  ⚠️  API returned HTTP ${HTTP_CODE}"
  fi
else
  echo "  ⚠️  Skipping — set DT_ENV_URL and DT_API_TOKEN"
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
echo "  • Audit log pipeline (Lambda → Log Ingest API)"
echo "  • Metric event alerts (3 log-based alerts)"
echo "  • Forensics dashboard (6 DQL tiles)"
echo "  • E2E verification passed"
echo ""
echo "Next steps:"
echo "  1. Configure alerting profiles for notification routing"
echo "  2. Review: ${DT_ENV_URL:-<url>}/ui/dashboards"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"

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

# ─── Step 2/4: Create Metric Events ─────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create log metric event alerts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${DT_ENV_URL:-}" ] && [ -n "${DT_API_TOKEN:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  DT_ENV_URL/DT_API_TOKEN not set — skipping."
fi
echo ""

# ─── Step 3/4: Import Forensics Dashboard ────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Import forensics dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${DT_ENV_URL:-}" ] && [ -n "${DT_API_TOKEN:-}" ]; then
  if [ -f "${DASHBOARDS_DIR}/forensics-investigation.json" ]; then
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "${DT_ENV_URL}/api/config/v1/dashboards" \
      -H "Content-Type: application/json" \
      -H "Authorization: Api-Token ${DT_API_TOKEN}" \
      -d @"${DASHBOARDS_DIR}/forensics-investigation.json")
    [ "${HTTP}" = "201" ] && echo "  ✅ Dashboard created" || echo "  ⚠️  HTTP ${HTTP}"
  fi
else
  echo "  ⚠️  Skipping — credentials not set."
fi
echo ""

# ─── Step 4/4: Verify ────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4/4: E2E verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bash "${SCRIPT_DIR}/verify.sh"

echo ""
echo "============================================================"
echo "✅ Dynatrace full observability setup complete!"
echo "============================================================"
