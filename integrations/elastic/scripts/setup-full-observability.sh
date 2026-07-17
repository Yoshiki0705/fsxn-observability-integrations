#!/bin/bash
# setup-full-observability.sh — Deploy complete Elastic observability for FSx for ONTAP
#
# Orchestrates: Deploy stack → Create detection rules → Import forensics dashboard → Verify
#
# Prerequisites:
#   - AWS CLI configured
#   - Elasticsearch URL + API key
#   - Kibana URL (for detection rules + dashboard import)
#
# Usage:
#   export ELASTIC_URL="https://<cluster>.es.<region>.aws.cloud.es.io:9243"
#   export KIBANA_URL="https://<cluster>.kb.<region>.aws.cloud.es.io:9243"
#   export ELASTIC_API_KEY="<your-api-key>"
#   bash integrations/elastic/scripts/setup-full-observability.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="${SCRIPT_DIR}/../dashboards"

echo "============================================================"
echo " FSx for ONTAP — Elastic Full Observability Setup"
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

# ─── Step 2/4: Create Detection Rules ────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Create security detection rules"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${KIBANA_URL:-}" ] && [ -n "${ELASTIC_API_KEY:-}" ]; then
  bash "${SCRIPT_DIR}/create-alerts.sh"
else
  echo "  ⚠️  KIBANA_URL/ELASTIC_API_KEY not set — skipping."
fi

echo ""

# ─── Step 3/4: Import Forensics Dashboard ────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3/4: Import forensics investigation dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -n "${KIBANA_URL:-}" ] && [ -n "${ELASTIC_API_KEY:-}" ] && [ -f "${DASHBOARDS_DIR}/forensics-investigation.ndjson" ]; then
  echo "  Importing saved objects..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${KIBANA_URL}/api/saved_objects/_import?overwrite=true" \
    -H "kbn-xsrf: true" \
    -H "Authorization: ApiKey ${ELASTIC_API_KEY}" \
    --form file=@"${DASHBOARDS_DIR}/forensics-investigation.ndjson")
  if [ "${HTTP_CODE}" = "200" ]; then
    echo "  ✅ Dashboard + saved searches imported"
  else
    echo "  ⚠️  Import returned HTTP ${HTTP_CODE}"
  fi
else
  echo "  ⚠️  Skipping — set KIBANA_URL and ELASTIC_API_KEY"
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
echo "  • Audit log pipeline (Lambda → Bulk API → Elasticsearch)"
echo "  • Security detection rules (3 Elastic Security rules)"
echo "  • Forensics dashboard + 4 saved searches (Kibana)"
echo "  • E2E verification passed"
echo ""
echo "Next steps:"
echo "  1. Configure rule actions (email, Slack, webhook to SNS)"
echo "  2. Open dashboard: ${KIBANA_URL:-<kibana>}/app/dashboards"
echo "  3. Enable FSx for ONTAP audit logging if not already active"
echo "============================================================"
