#!/bin/bash
# setup-full-observability.sh — Deploy complete Grafana Cloud observability for FSx for ONTAP
#
# Orchestrates: Deploy stack → Create alerts → Deploy forensics dashboard → Verify
#
# Prerequisites:
#   - AWS CLI configured
#   - Grafana Cloud credentials (Instance ID + API key)
#   - Service Account token for dashboard/alert provisioning
#
# Usage:
#   export GRAFANA_URL="https://your-instance.grafana.net"
#   export GRAFANA_INSTANCE_ID="<instance-id>"
#   export GRAFANA_API_KEY="<cloud-api-key>"
#   export GRAFANA_SA_TOKEN="glsa_xxxx"
#   export GRAFANA_REGION="prod-ap-southeast-1"
#   bash integrations/grafana/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " FSx for ONTAP — Grafana Cloud Full Observability Setup"
echo "============================================================"
echo ""

# ─── Step 1/4: Deploy CloudFormation Stack ───────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1/4: Deploy audit log pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f "${SCRIPT_DIR}/deploy.sh" ]; then
  bash "${SCRIPT_DIR}/deploy.sh"
else
  echo "  ⚠️  deploy.sh not found — skipping CloudFormation deployment."
  echo "     Deploy manually: aws cloudformation deploy --template-file template.yaml ..."
fi

echo ""

# ─── Step 2/4: Create Security Alerts ────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create security alert rules"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${GRAFANA_SA_TOKEN:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  GRAFANA_SA_TOKEN not set — skipping alert creation."
  echo "     Set it and run: bash scripts/create-alerts.sh"
fi

echo ""

# ─── Step 3/4: Deploy Forensics Dashboard ────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Deploy forensics investigation dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${GRAFANA_SA_TOKEN:-}" ]; then
  bash "${SCRIPT_DIR}/deploy-forensics-dashboard.sh"
else
  echo "  ⚠️  GRAFANA_SA_TOKEN not set — skipping dashboard deployment."
  echo "     Set it and run: bash scripts/deploy-forensics-dashboard.sh"
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
echo "  • Audit log pipeline (Lambda → OTLP Gateway → Loki)"
echo "  • Security alerts (3 rules: ARP, mass delete, failed access)"
echo "  • Forensics investigation dashboard (4-step workflow)"
echo "  • E2E verification passed"
echo ""
echo "Next steps:"
echo "  1. Configure alert contact points (Grafana UI → Alerting)"
echo "  2. Review dashboard: ${GRAFANA_URL:-<your-url>}/d/fsxn-forensics-investigation"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"
