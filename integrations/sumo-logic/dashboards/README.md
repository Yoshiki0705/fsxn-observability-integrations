# Sumo Logic Forensic Investigation Dashboard

DII Storage Workload Security equivalent forensic investigation views for FSx for ONTAP audit logs in Sumo Logic.

## Prerequisites

- FSx for ONTAP audit logs shipped to Sumo Logic via the `integrations/sumo-logic/` pipeline
- Source Category: `fsxn*` (default from the Lambda handler)
- Sumo Logic Enterprise or Trial account (Dashboard API access)

## Deploy via Content API

```bash
# Set credentials
export SUMO_ACCESS_ID="<your-access-id>"
export SUMO_ACCESS_KEY="<your-access-key>"
export SUMO_API_ENDPOINT="https://api.sumologic.com/api"  # or .eu, .au, .jp, etc.

# Import dashboard
curl -X POST "${SUMO_API_ENDPOINT}/v2/dashboards" \
  -H "Content-Type: application/json" \
  -u "${SUMO_ACCESS_ID}:${SUMO_ACCESS_KEY}" \
  -d @forensics-investigation.json
```

Or use the Sumo Logic UI: **App Catalog → Import** or copy queries manually into a new Dashboard.

## Panels

| Panel | Investigation Step | Purpose |
|-------|-------------------|---------|
| User Activity Timeline | Step 1 | Activity volume for a specific user over time |
| All Activity | Step 2 | Full event stream (table) filtered by user |
| Client IP — Access Origins | Step 3 | Source IPs with unique file counts |
| File Entity History | Step 4 | All operations on a specific file path |
| Top Affected Volumes | — | Bar chart of volumes by event count |
| ARP Alert Timeline | — | Ransomware detection events over time |

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{user}}` | Windows/AD username to investigate | `CORP\jdoe` or `*` for all |
| `{{path}}` | File path to investigate | `/vol_data/finance/report.xlsx` |

## Query Language Reference

Sumo Logic Log Search syntax for the 4-step investigation workflow:

| Step | Query Pattern |
|------|--------------|
| User filter | `\| where user = "CORP\\jdoe"` |
| Time sort | `\| sort _messagetime desc` |
| IP filter | `\| where client_ip = "198.51.100.99"` |
| Path filter | `\| where path = "/vol_data/finance/report.xlsx"` |
| JSON parse | `\| json field=_raw "user", "operation", "path", "client_ip"` |
| Aggregation | `\| count by <field>` or `\| timeslice 5m \| count by _timeslice` |

## Equivalent on Other Vendors

| Vendor | Artifact |
|--------|----------|
| Datadog | [`integrations/datadog/dashboards/forensics-dashboard.json`](../../datadog/dashboards/) |
| Grafana | [`integrations/grafana/dashboards/forensics-investigation.json`](../../grafana/dashboards/forensics-investigation.json) |
| Splunk | [`integrations/splunk-serverless/searches/*.spl`](../../splunk-serverless/searches/) |
| Elastic | [`integrations/elastic/dashboards/forensics-investigation.ndjson`](../../elastic/dashboards/) |

> See [AWS-Native Alternative Matrix — Forensics Per-Vendor Reference](../../../docs/en/native-alternative-matrix.md#forensics-dashboard--per-vendor-reference) for the full comparison.
