# Backend Parity Matrix

## Verified Attribute Visibility (2026-05-19)

| Attribute | Datadog | Grafana Cloud (Loki) | Honeycomb |
|-----------|---------|---------------------|-----------|
| `service.name` | ✅ Visible as `service` tag | ✅ Resource label `service_name` | ✅ Column `service.name` |
| `cloud.provider` | ✅ Attribute | ✅ Resource label | ✅ Column |
| `cloud.platform` | ✅ Attribute | ✅ Resource label | ✅ Column |
| `event.type` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `user.name` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `client.address` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `fsxn.operation` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `fsxn.path` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `fsxn.result` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `fsxn.svm` | ✅ Attribute | ✅ Detected field | ✅ Column |
| `severityText` | ✅ Maps to log status | ✅ `level` label | ✅ Column |
| `severityNumber` | ✅ Internal mapping | ✅ Numeric level | ✅ Column |

## Backend-Specific Behaviors

| Behavior | Datadog | Grafana Cloud | Honeycomb |
|----------|---------|---------------|-----------|
| Timestamp acceptance | 18h past (documented) | Recent preferred | Recent preferred |
| Max payload size | 5MB | ~4MB recommended | 5MB |
| Auth method | DD-API-KEY header | Basic Auth (OTLP gateway) | x-honeycomb-team header |
| Exporter type | `datadog` (dedicated) | `otlp_http` (generic) | `otlp_http` (generic) |
| Ingestion delay | Seconds | Seconds | Seconds |
| Default retention | 15 days | 30 days (free tier) | 60 days (free tier) |

## Query Examples by Backend

### Find failed access attempts

| Backend | Query |
|---------|-------|
| Datadog | `source:fsxn-audit @attributes.fsxn.result:Failure` |
| Grafana (Loki) | `{service_name="fsxn-audit"} |= "Failure"` |
| Honeycomb | Dataset: `fsxn-audit`, WHERE `fsxn.result` = `Failure` |
