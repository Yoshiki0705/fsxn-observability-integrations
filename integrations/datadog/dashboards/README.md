# Datadog Forensics Dashboard

DII Storage Workload Security equivalent dashboard for FSx for ONTAP audit forensics.

## Prerequisites

- Datadog audit log pipeline deployed and shipping logs
- Datadog API key and Application key

## Log Source Tags (ddsource mapping)

This dashboard queries logs using Datadog's `source:` filter. The source tags are set by each Lambda handler's `ddsource` field:

| Pipeline | Lambda Handler | `ddsource` value | Dashboard query |
|----------|---------------|:----------------:|-----------------|
| Audit logs (S3 AP) | `handler.py` | `fsxn` | `source:fsxn` |
| EMS webhook | `ems_handler.py` | `fsxn-ems` | `source:fsxn-ems` |
| FPolicy (SQS) | `fpolicy_handler.py` | `fsxn-fpolicy` | `source:fsxn-fpolicy` |

The audit log handler's source is configurable via the `DD_SOURCE` environment variable (default: `fsxn`). If you override it, update the dashboard queries accordingly.

The "File Access Audit Trail" and "Client IP Origins" widgets query all three sources (`source:fsxn OR source:fsxn-ems OR source:fsxn-fpolicy`) to provide a unified view.

## Deploy via Datadog API

```bash
# Set credentials
export DD_SITE="ap1.datadoghq.com"   # or us5.datadoghq.com, datadoghq.eu, etc.
export DD_API_KEY="<your-api-key>"
export DD_APP_KEY="<your-app-key>"

# Create dashboard
curl -X POST "https://api.${DD_SITE}/api/v1/dashboard" \
  -H "Content-Type: application/json" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
  -d @forensics-dashboard.json
```

## Widgets

| Widget | DII Equivalent | Purpose |
|--------|---------------|---------|
| ARP Alert Timeline | Alert timeline | Visualize anomaly detection events over time |
| Incident Response Actions | Response log | Track block/snapshot/disconnect actions |
| Top Affected Volumes | Affected assets | Identify which volumes are under attack |
| Alert Severity Distribution | Severity breakdown | Prioritize response by severity |
| User Activity | User timeline | Per-user file operation frequency |
| File Access Audit Trail | Forensics table | Detailed event log with user, path, IP, SVM |
| Client IP Origins | Access map | Identify unusual source IPs |
| Recovery Verification | Verification status | Track clean/suspicious verdicts |

## Customization

- **Template variables**: Filter by SVM (`$svm`) or user (`$user`)
- **Log source**: Widgets use `source:fsxn` (audit), `source:fsxn-ems`, or `source:fsxn-fpolicy`. If you changed the `DD_SOURCE` environment variable in your Lambda, update the queries to match.
- **Facets**: Ensure `@usr.name`, `@evt.name`, `@file.path`, `@network.client.ip`, `@svm`, `@volume`, `@severity`, `@action`, `@verdict` facets exist in your Datadog Logs configuration

## Equivalent Dashboards on Other Vendors

This Datadog dashboard is one implementation of the **vendor-neutral forensics investigation workflow**. The same views (user timeline, file access trail, IP drill-down, affected volumes, severity distribution) can be built on any vendor receiving FSx for ONTAP audit logs.

| Vendor | Provided Artifact | Query Language | Notes |
|--------|-------------------|:-------------:|-------|
| **Grafana (Loki)** | [`integrations/grafana/dashboards/forensics-investigation.json`](../../../integrations/grafana/dashboards/forensics-investigation.json) | LogQL | Full dashboard JSON; import via Grafana API or UI |
| **Elastic (Kibana)** | [Setup Guide — Forensic Investigation](../../../integrations/elastic/docs/en/setup-guide.md#forensic-investigation-kibana-discoverlens) | KQL | Saved Searches + Lens; ECS field mapping pre-defined |
| **Splunk** | SPL queries in [Cyber Resilience Map](../../../docs/en/cyber-resilience-capability-map.md) | SPL | 4 saved searches composable into Dashboard Studio |
| **Sumo Logic** | Same query patterns (adapted syntax) | Sumo Query | Log Search dashboards via Content API |

### Investigation Workflow (Vendor-Independent)

Regardless of which vendor you use, the forensics investigation follows the same 4-step flow:

1. **User Overview** — Filter by suspected user, view activity volume over time
2. **All Activity** — Full event stream for the user/time window (what files, what operations)
3. **IP Drill-Down** — Identify access source IPs, detect unusual origins
4. **File Entity History** — Trace all operations on a specific file path

The difference is only the query language:

| Step | Datadog | Grafana (LogQL) | Elastic (KQL) | Splunk (SPL) |
|------|---------|-----------------|---------------|--------------|
| User filter | `@usr.name:<user>` | `{source="fsxn"} \| json \| user=~"<user>"` | `user.name: "<user>"` | `index=fsxn_audit user="<user>"` |
| Time sort | Default (newest first) | Default | `@timestamp` desc | `_time` desc |
| IP filter | `@network.client.ip:<ip>` | `\| client_ip=~"<ip>"` | `source.ip: "<ip>"` | `client_ip="<ip>"` |
| Path filter | `@file.path:<path>` | `\| path=~"<path>"` | `file.path: "<path>"` | `path="<path>"` |

> **Choosing a vendor**: If you already have audit logs flowing to a specific vendor via this project's integration templates, build the forensics dashboard there. No need to add a second vendor just for forensics.
