#!/bin/bash
# setup-full-observability.sh — Deploy complete Honeycomb observability
#
# Orchestrates: Deploy → Triggers → Verify
#
# Usage:
#   export HONEYCOMB_API_KEY="hcaik_xxxx"
#   export HONEYCOMB_DATASET="fsxn-audit"
#   bash integrations/honeycomb/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " FSx for ONTAP — Honeycomb Full Observability Setup"
echo "============================================================"
echo ""

# ─── Step 1/3: Deploy CloudFormation Stack ───────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1/3: Deploy audit log pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f "${SCRIPT_DIR}/deploy.sh" ]; then
  bash "${SCRIPT_DIR}/deploy.sh"
else
  echo "  ⚠️  deploy.sh not found — skipping."
fi

echo ""

# ─── Step 2/3: Create Triggers (Alerts) ──────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/3: Create security triggers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${HONEYCOMB_API_KEY:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  HONEYCOMB_API_KEY not set — skipping."
fi

echo ""

# ─── Step 3/3: Verify End-to-End ─────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/3: E2E verification (send test event)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bash "${SCRIPT_DIR}/verify.sh"

echo ""
echo "============================================================"
echo "✅ Full observability setup complete!"
echo ""
echo "What was configured:"
echo "  • Audit log pipeline (Lambda → Events Batch API)"
echo "  • Security triggers (3 triggers)"
echo "  • E2E verification passed"
echo ""
echo "Note: Honeycomb is optimized for distributed tracing and"
echo "high-cardinality event exploration. For forensics dashboards"
echo "(user timeline, file access audit trail), use one of the"
echo "other supported vendors (Datadog, Grafana, Splunk, Elastic,"
echo "Sumo Logic, New Relic, Dynatrace)."
echo ""
echo "Next steps:"
echo "  1. Add trigger recipients (Slack, PagerDuty, webhook)"
echo "  2. Query: https://ui.honeycomb.io/ → Dataset: ${HONEYCOMB_DATASET:-fsxn-audit}"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"

# ─── Step 1/3: Deploy CloudFormation Stack ───────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1/3: Deploy audit log pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f "${SCRIPT_DIR}/deploy.sh" ]; then
  bash "${SCRIPT_DIR}/deploy.sh"
else
  echo "  ⚠️  deploy.sh not found — skipping."
fi
echo ""

# ─── Step 2/3: Create Triggers ───────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/3: Create security triggers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${HONEYCOMB_API_KEY:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  HONEYCOMB_API_KEY not set — skipping."
fi
echo ""

# ─── Step 3/3: Verify ────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/3: E2E verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bash "${SCRIPT_DIR}/verify.sh"

echo ""
echo "============================================================"
echo "✅ Honeycomb full observability setup complete!"
echo ""
echo "Note: Honeycomb excels at distributed tracing and"
echo "high-cardinality exploration. For forensics dashboards,"
echo "use Datadog/Grafana/Splunk/Elastic/Sumo Logic/New Relic/Dynatrace."
echo "============================================================"
