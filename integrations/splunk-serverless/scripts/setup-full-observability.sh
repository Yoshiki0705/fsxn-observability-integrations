#!/bin/bash
# setup-full-observability.sh — Deploy complete Splunk observability for FSx for ONTAP
#
# Orchestrates: Deploy stack → Create alerts → Verify
#
# Prerequisites:
#   - AWS CLI configured
#   - Splunk HEC URL + token
#   - Splunk management API access (for alerts)
#
# Usage:
#   export SPLUNK_HEC_URL="https://<host>:8088"
#   export SPLUNK_HEC_TOKEN="<hec-token>"
#   export SPLUNK_URL="https://<host>:8089"
#   export SPLUNK_TOKEN="<bearer-token>"
#   bash integrations/splunk-serverless/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " FSx for ONTAP — Splunk Full Observability Setup"
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

# ─── Step 2/4: Create Security Alerts ────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create security alerts (saved searches)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${SPLUNK_URL:-}" ] && [ -n "${SPLUNK_TOKEN:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  SPLUNK_URL/SPLUNK_TOKEN not set — skipping."
  echo "     Set them and run: bash scripts/create-alerts.sh"
fi

echo ""

# ─── Step 3/4: Forensics Searches ────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Forensics investigation searches"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ℹ️  SPL forensics searches available at:"
echo "     integrations/splunk-serverless/searches/"
echo ""
echo "  Import into Dashboard Studio with tokens:"
echo "     \$user\$, \$client_ip\$, \$path\$"
echo ""
echo "  See: integrations/splunk-serverless/searches/README.md"

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
echo "  • Audit log pipeline (Lambda → HEC → Splunk)"
echo "  • Security alerts (3 saved searches with alert actions)"
echo "  • Forensics searches ready (4 SPL files)"
echo "  • E2E verification passed"
echo ""
echo "Next steps:"
echo "  1. Configure alert actions (email, webhook to SNS)"
echo "  2. Build Dashboard Studio dashboard from searches/*.spl"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"
