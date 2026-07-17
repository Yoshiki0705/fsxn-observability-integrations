# Dynatrace Forensic Investigation Dashboard

DII Storage Workload Security equivalent forensic investigation views for FSx for ONTAP audit logs in Dynatrace.

## Prerequisites

- FSx for ONTAP audit logs shipped to Dynatrace via the `integrations/dynatrace/` pipeline
- Log attribute: `log.source = "fsxn"` (set by the Lambda handler)
- Dynatrace SaaS or Managed with Log Management and Analytics (Grail)

## Deploy via Dynatrace API

```bash
# Set credentials
export DT_ENV_URL="https://<env-id>.live.dynatrace.com"
export DT_API_TOKEN="<your-api-token>"  # Scope: Write dashboards

# Create dashboard
curl -X POST "${DT_ENV_URL}/api/config/v1/dashboards" \
  -H "Content-Type: application/json" \
  -H "Authorization: Api-Token ${DT_API_TOKEN}" \
  -d @forensics-investigation.json
```

Or use the Dynatrace UI: **Observe → Dashboards → Import**.

## DQL Investigation Queries

Dynatrace Query Language (DQL) queries for the 4-step forensic workflow:

### Step 1: User Overview
```dql
fetch logs
| filter matchesValue(log.source, "fsxn")
| filter matchesValue(user, "CORP\\jdoe")
| makeTimeseries count(), by:{operation}, interval:5m
```

### Step 2: All Activity
```dql
fetch logs
| filter matchesValue(log.source, "fsxn")
| filter matchesValue(user, "CORP\\jdoe")
| fields timestamp, user, operation, path, client_ip, result, svm, volume
| sort timestamp desc
| limit 200
```

### Step 3: IP Drill-Down
```dql
fetch logs
| filter matchesValue(log.source, "fsxn")
| filter isNotNull(client_ip)
| summarize event_count = count(), unique_files = countDistinct(path), by:{client_ip}
| sort event_count desc
| limit 20
```

### Step 4: File Entity History
```dql
fetch logs
| filter matchesValue(log.source, "fsxn")
| filter matchesValue(path, "/vol_data/finance/report.xlsx")
| fields timestamp, user, operation, client_ip, result, svm
| sort timestamp desc
| limit 200
```

## Tiles

| Tile | Purpose |
|------|---------|
| User Activity Timeline | Activity volume by operation (timeseries) |
| All Activity | Full event stream (table) |
| Client IP — Access Origins | Source IPs with unique file counts |
| File Entity History | All operations on a specific file |
| Top Affected Volumes | Volumes ranked by event count |
| ARP Alert Timeline | Ransomware detection events |

## Equivalent on Other Vendors

| Vendor | Artifact |
|--------|----------|
| Datadog | [`integrations/datadog/dashboards/forensics-dashboard.json`](../../datadog/dashboards/) |
| Grafana | [`integrations/grafana/dashboards/forensics-investigation.json`](../../grafana/dashboards/forensics-investigation.json) |
| Splunk | [`integrations/splunk-serverless/searches/*.spl`](../../splunk-serverless/searches/) |
| Elastic | [`integrations/elastic/dashboards/forensics-investigation.ndjson`](../../elastic/dashboards/) |
| Sumo Logic | [`integrations/sumo-logic/dashboards/forensics-investigation.json`](../../sumo-logic/dashboards/) |
| New Relic | [`integrations/new-relic/dashboards/forensics-investigation.json`](../../new-relic/dashboards/) |
