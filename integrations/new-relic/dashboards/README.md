# New Relic Forensic Investigation Dashboard

DII Storage Workload Security equivalent forensic investigation views for FSx for ONTAP audit logs in New Relic.

## Prerequisites

- FSx for ONTAP audit logs shipped to New Relic via the `integrations/new-relic/` pipeline
- Log attribute: `instrumentation.provider = 'fsxn'`
- New Relic account with Logs and Dashboards access

## Deploy via NerdGraph API

```bash
# Set credentials
export NEW_RELIC_API_KEY="<your-user-api-key>"
export NEW_RELIC_ACCOUNT_ID="<your-account-id>"

# Create dashboard via NerdGraph
curl -X POST 'https://api.newrelic.com/graphql' \
  -H "Content-Type: application/json" \
  -H "API-Key: ${NEW_RELIC_API_KEY}" \
  -d "{
    \"query\": \"mutation { dashboardCreate(accountId: ${NEW_RELIC_ACCOUNT_ID}, dashboard: \$dashboard) { entityResult { guid name } errors { description } } }\",
    \"variables\": { \"dashboard\": $(cat forensics-investigation.json) }
  }"
```

Or use the New Relic UI: **Dashboards → Import dashboard** → paste the JSON content.

## NRQL Investigation Queries

### Step 1: User Overview
```sql
SELECT count(*) FROM Log
WHERE instrumentation.provider = 'fsxn' AND user = 'CORP\\jdoe'
FACET operation TIMESERIES 5 minutes SINCE 24 hours ago
```

### Step 2: All Activity
```sql
SELECT timestamp, user, operation, path, client_ip, result, svm, volume
FROM Log WHERE instrumentation.provider = 'fsxn' AND user = 'CORP\\jdoe'
ORDER BY timestamp DESC LIMIT 200
```

### Step 3: IP Drill-Down
```sql
SELECT count(*), uniqueCount(path) as 'Unique Files'
FROM Log WHERE instrumentation.provider = 'fsxn'
FACET client_ip SINCE 24 hours ago LIMIT 20
```

### Step 4: File Entity History
```sql
SELECT timestamp, user, operation, client_ip, result, svm
FROM Log WHERE instrumentation.provider = 'fsxn'
AND path = '/vol_data/finance/report.xlsx'
ORDER BY timestamp DESC LIMIT 200
```

## Panels

| Panel | Purpose |
|-------|---------|
| User Activity Timeline | Activity volume per operation type over time |
| Client IP — Access Origins | Top source IPs by event count |
| All Activity | Full event stream table |
| Top Affected Volumes | Volumes ranked by event count |
| ARP Alert Timeline | Ransomware detection events |
| Alert Severity Distribution | Pie chart of event severities |
| Incident Response Actions | Block/snapshot/disconnect actions over time |

## Equivalent on Other Vendors

| Vendor | Artifact |
|--------|----------|
| Datadog | [`integrations/datadog/dashboards/forensics-dashboard.json`](../../datadog/dashboards/) |
| Grafana | [`integrations/grafana/dashboards/forensics-investigation.json`](../../grafana/dashboards/forensics-investigation.json) |
| Splunk | [`integrations/splunk-serverless/searches/*.spl`](../../splunk-serverless/searches/) |
| Elastic | [`integrations/elastic/dashboards/forensics-investigation.ndjson`](../../elastic/dashboards/) |
| Sumo Logic | [`integrations/sumo-logic/dashboards/forensics-investigation.json`](../../sumo-logic/dashboards/) |
