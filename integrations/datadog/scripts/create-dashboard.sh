#!/bin/bash
# Create FSx for ONTAP Audit Log Dashboard via Datadog API
#
# Prerequisites:
#   - Datadog API Key and Application Key
#   - Logs flowing to Datadog with source:fsxn
#
# Usage:
#   export DD_API_KEY="your-api-key"
#   export DD_APP_KEY="your-app-key"
#   export DD_SITE="ap1.datadoghq.com"  # or datadoghq.com, datadoghq.eu, etc.
#   bash integrations/datadog/scripts/create-dashboard.sh
#
# Reference:
#   https://docs.datadoghq.com/api/latest/dashboards/

set -euo pipefail

DD_API_KEY="${DD_API_KEY:-}"
DD_APP_KEY="${DD_APP_KEY:-}"
DD_SITE="${DD_SITE:-ap1.datadoghq.com}"

if [ -z "${DD_API_KEY}" ] || [ -z "${DD_APP_KEY}" ]; then
  echo "ERROR: DD_API_KEY and DD_APP_KEY must be set."
  echo ""
  echo "To get your keys:"
  echo "  1. Go to https://${DD_SITE}/organization-settings/api-keys"
  echo "  2. Copy your API Key"
  echo "  3. Go to https://${DD_SITE}/organization-settings/application-keys"
  echo "  4. Create or copy an Application Key"
  echo "  5. export DD_API_KEY='...'"
  echo "  6. export DD_APP_KEY='...'"
  echo "  7. Re-run this script"
  exit 1
fi

DD_API_URL="https://api.${DD_SITE}"

echo "=== Creating FSx for ONTAP Audit Log Dashboard ==="
echo "Datadog Site: ${DD_SITE}"
echo "API URL: ${DD_API_URL}"
echo ""

PAYLOAD=$(cat << 'EOF'
{
  "title": "FSx for ONTAP Audit Log Dashboard",
  "description": "Serverless audit log pipeline monitoring for FSx for ONTAP",
  "layout_type": "ordered",
  "widgets": [
    {
      "definition": {
        "title": "Log Volume (5m intervals)",
        "type": "timeseries",
        "requests": [
          {
            "queries": [
              {
                "data_source": "logs",
                "name": "query1",
                "indexes": ["*"],
                "compute": {"aggregation": "count"},
                "group_by": [],
                "search": {"query": "source:fsxn"}
              }
            ],
            "response_format": "timeseries",
            "display_type": "bars"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Operations Breakdown",
        "type": "toplist",
        "requests": [
          {
            "queries": [
              {
                "data_source": "logs",
                "name": "query1",
                "indexes": ["*"],
                "compute": {"aggregation": "count"},
                "group_by": [{"facet": "@attributes.operation", "limit": 10, "sort": {"aggregation": "count", "order": "desc"}}],
                "search": {"query": "source:fsxn"}
              }
            ],
            "response_format": "scalar"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Top Users by Activity",
        "type": "toplist",
        "requests": [
          {
            "queries": [
              {
                "data_source": "logs",
                "name": "query1",
                "indexes": ["*"],
                "compute": {"aggregation": "count"},
                "group_by": [{"facet": "@attributes.user", "limit": 10, "sort": {"aggregation": "count", "order": "desc"}}],
                "search": {"query": "source:fsxn"}
              }
            ],
            "response_format": "scalar"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Failed Access Attempts",
        "type": "timeseries",
        "requests": [
          {
            "queries": [
              {
                "data_source": "logs",
                "name": "query1",
                "indexes": ["*"],
                "compute": {"aggregation": "count"},
                "group_by": [],
                "search": {"query": "source:fsxn @attributes.result:Failure"}
              }
            ],
            "response_format": "timeseries",
            "display_type": "bars",
            "style": {"palette": "warm"}
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Access by SVM",
        "type": "toplist",
        "requests": [
          {
            "queries": [
              {
                "data_source": "logs",
                "name": "query1",
                "indexes": ["*"],
                "compute": {"aggregation": "count"},
                "group_by": [{"facet": "@attributes.svm", "limit": 10, "sort": {"aggregation": "count", "order": "desc"}}],
                "search": {"query": "source:fsxn"}
              }
            ],
            "response_format": "scalar"
          }
        ]
      }
    },
    {
      "definition": {
        "title": "Pipeline Health: Lambda Errors",
        "type": "query_value",
        "requests": [
          {
            "queries": [
              {
                "data_source": "metrics",
                "name": "query1",
                "query": "sum:aws.lambda.errors{functionname:fsxn-*}.as_count()"
              }
            ],
            "response_format": "scalar"
          }
        ],
        "precision": 0
      }
    }
  ],
  "tags": ["fsxn", "ontap", "audit", "serverless"]
}
EOF
)

RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${DD_API_URL}/api/v1/dashboard" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  DASHBOARD_URL=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "")
  DASHBOARD_ID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || echo "")
  echo "=== Dashboard Created Successfully ==="
  echo "Dashboard URL: https://${DD_SITE}${DASHBOARD_URL}"
  echo "Dashboard ID: ${DASHBOARD_ID}"
  echo ""
  echo "Widgets:"
  echo "  1. Log Volume (timeseries)"
  echo "  2. Operations Breakdown (toplist)"
  echo "  3. Top Users by Activity (toplist)"
  echo "  4. Failed Access Attempts (timeseries)"
  echo "  5. Access by SVM (toplist)"
  echo "  6. Pipeline Health: Lambda Errors (query_value)"
else
  echo "ERROR: Failed to create dashboard (HTTP ${HTTP_CODE})"
  echo "Response: ${BODY}"
  echo ""
  echo "Common issues:"
  echo "  - Invalid API/App key"
  echo "  - Wrong DD_SITE (try datadoghq.com or ap1.datadoghq.com)"
  exit 1
fi
