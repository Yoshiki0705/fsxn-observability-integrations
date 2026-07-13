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
