# Elastic (Kibana) Forensic Investigation Dashboard

DII Storage Workload Security equivalent forensic investigation views for FSx for ONTAP audit logs in Elasticsearch/Kibana.

## Prerequisites

- FSx for ONTAP audit logs shipped to Elasticsearch via the `integrations/elastic/` pipeline
- Index pattern: `fsxn-audit-*` (ECS-mapped fields)
- Kibana 8.x+

## Import

```bash
# Import saved objects via Kibana API
curl -X POST "https://<kibana-host>:5601/api/saved_objects/_import" \
  -H "kbn-xsrf: true" \
  -H "Authorization: ApiKey <your-api-key>" \
  --form file=@forensics-investigation.ndjson
```

Or use the Kibana UI: **Stack Management → Saved Objects → Import** → select `forensics-investigation.ndjson`.

## Contents

The NDJSON file contains 5 saved objects:

| Object | Type | Purpose |
|--------|------|---------|
| `fsxn-forensics-user-overview` | Saved Search | Step 1: Filter by `user.name` to see all activity for a user |
| `fsxn-forensics-all-activity` | Saved Search | Step 2: Full event stream sorted by timestamp |
| `fsxn-forensics-ip-drill-down` | Saved Search | Step 3: Filter by `source.ip` for access origin analysis |
| `fsxn-forensics-file-entity-history` | Saved Search | Step 4: Filter by `file.path` for file operation history |
| `fsxn-forensics-dashboard` | Dashboard | Combines all 4 saved searches in a single view |

## ECS Field Mapping

This project maps ONTAP audit/FPolicy fields to Elastic Common Schema (ECS):

| ONTAP Field | ECS Field | Used In |
|------------|-----------|---------|
| UserName / user | `user.name` | User Overview, All Activity |
| ClientIP / client_ip | `source.ip` | IP Drill-Down |
| ObjectName / path | `file.path` | File Entity History |
| Operation / operation | `event.action` | All views |
| Result | `event.outcome` | All views |
| SVM / vserver | `observer.name` | All views |

## Investigation Workflow

Same 4-step flow as all vendors in this project:

1. **User Overview** — `user.name: "CORP\\jdoe"` → see activity volume
2. **All Activity** — No filter, sorted `@timestamp` desc → full event stream
3. **IP Drill-Down** — `source.ip: "198.51.100.99"` → identify unusual origins
4. **File Entity History** — `file.path: "/vol_data/finance/report.xlsx"` → all operations on a file

## Adding Lens Visualizations

After import, enhance the dashboard with Lens panels:

1. Open the imported dashboard in Kibana
2. Click **Edit** → **Create visualization**
3. Add a **Bar chart** with:
   - X-axis: `event.action` (Top values)
   - Break down by: `user.name`
   - Filter: `event.dataset: "fsxn"`

This surfaces anomalous action distribution (e.g., delete spikes) similar to DII SWS's Forensics UI.

## Equivalent on Other Vendors

| Vendor | Artifact |
|--------|----------|
| Datadog | [`integrations/datadog/dashboards/forensics-dashboard.json`](../../datadog/dashboards/) |
| Grafana | [`integrations/grafana/dashboards/forensics-investigation.json`](../../grafana/dashboards/forensics-investigation.json) |
| Splunk | [`integrations/splunk-serverless/searches/*.spl`](../../splunk-serverless/searches/) |
| Sumo Logic | [`integrations/sumo-logic/dashboards/`](../../sumo-logic/dashboards/) |

> See [AWS-Native Alternative Matrix — Forensics Per-Vendor Reference](../../../docs/en/native-alternative-matrix.md#forensics-dashboard--per-vendor-reference) for the full comparison.
