# ONTAP Telemetry Delivery Matrix

🌐 [日本語](../ja/ontap-telemetry-delivery-matrix.md) | **English** (this page)

## Delivery Path Overview

ONTAP telemetry can reach observability backends via two paths:

| Path | Description | Pros | Cons |
|------|-------------|------|------|
| **Direct Send** | Lambda → Backend API | Simple, fewer components | Single backend, no fan-out |
| **OTel Collector** | Lambda → Collector → Backend(s) | Multi-backend, centralized config | Additional infrastructure |

## Source × Delivery Path × Backend Matrix

### Audit Logs

| Backend | Direct Send | OTel Collector | Best For |
|---------|-------------|----------------|----------|
| **Datadog** | ✅ Lambda → Logs API | ✅ otlp_http/datadog | Compliance dashboards, log analytics |
| **Splunk** | ✅ Lambda → HEC | ✅ splunk_hec exporter | SIEM correlation, investigation |
| **Grafana** | ✅ Lambda → Loki API | ✅ otlp_http/grafana | Cost-effective long-term search |
| **Honeycomb** | ✅ Lambda → Events API | ✅ otlp_http/honeycomb | High-cardinality exploration |
| **Elastic** | ✅ Lambda → Bulk API | ✅ elasticsearch exporter | Full-text search, compliance |

### EMS / ARP (Security Events)

| Backend | Direct Send | OTel Collector | Best For |
|---------|-------------|----------------|----------|
| **Datadog** | ✅ Lambda → Logs API | ✅ otlp_http/datadog | Security monitoring, SIEM |
| **Splunk** | ✅ Lambda → HEC | ✅ splunk_hec exporter | SOC workflows, correlation |
| **Grafana** | ✅ Lambda → Loki API | ✅ otlp_http/grafana | Alert routing, on-call |
| **Honeycomb** | ✅ Lambda → Events API | ✅ otlp_http/honeycomb | Incident investigation |
| **Elastic** | ✅ Lambda → Bulk API | ✅ elasticsearch exporter | Security analytics |

### FPolicy (File Activity)

| Backend | Direct Send | OTel Collector | Best For |
|---------|-------------|----------------|----------|
| **Datadog** | ✅ Lambda → Logs API | ✅ otlp_http/datadog | Real-time file monitoring |
| **Splunk** | ✅ Lambda → HEC | ✅ splunk_hec exporter | Ransomware investigation |
| **Grafana** | ✅ Lambda → Loki API | ✅ otlp_http/grafana | File activity dashboards |
| **Honeycomb** | ✅ Lambda → Events API | ✅ otlp_http/honeycomb | Pattern analysis |
| **Elastic** | ✅ Lambda → Bulk API | ✅ elasticsearch exporter | File access analytics |

## service.name Mapping

Each telemetry source uses a distinct `service.name` for routing and identification:

| Source | service.name | event.type examples | Description |
|--------|-------------|--------------------:|-------------|
| Audit Logs | `fsxn-audit` | `file.read`, `file.write`, `file.delete` | CIFS/NFS file access audit |
| EMS / ARP | `fsxn-ems` | `ems.alert`, `arp.detected`, `arp.resolved` | System events, anti-ransomware |
| FPolicy | `fsxn-fpolicy` | `fpolicy.open`, `fpolicy.create`, `fpolicy.rename` | Real-time file operations |

### Collector Routing by service.name

```yaml
# OTel Collector config: route by service.name
processors:
  routing:
    from_attribute: service.name
    table:
      - value: fsxn-audit
        exporters: [otlp_http/datadog, otlp_http/grafana, otlp_http/splunk]
      - value: fsxn-ems
        exporters: [otlp_http/datadog, otlp_http/grafana]
      - value: fsxn-fpolicy
        exporters: [otlp_http/datadog, otlp_http/honeycomb]
```

## Backend-Specific Considerations

### Datadog

| Aspect | Detail |
|--------|--------|
| Field indexing | Auto-indexed: `service`, `status`, `host`. Custom: add facets for `event.type`, `svm.name` |
| Severity handling | Maps OTLP severity to Datadog `status` (info/warn/error/critical) |
| Timestamp window | Accepts events up to 18 hours in the past |
| Query syntax | `service:fsxn-audit @event.type:file.delete` |
| Max batch | 5 MB / 1000 items per request |

### Splunk

| Aspect | Detail |
|--------|--------|
| Field indexing | Define in `props.conf` / `transforms.conf`. Use `sourcetype=fsxn:audit` |
| Severity handling | Maps to Splunk `severity` field via HEC |
| Timestamp window | Configurable per index; default accepts any past timestamp |
| Query syntax | `index=fsxn sourcetype=fsxn:audit EventType=file.delete` |
| Max batch | No hard limit; recommend < 1 MB per event |

### Grafana (Loki via OTLP)

| Aspect | Detail |
|--------|--------|
| Field indexing | Labels: `service_name`, `event_type`. Structured metadata for high-cardinality fields |
| Severity handling | OTLP severity maps to `detected_level` label |
| Timestamp window | Rejects events > 1 hour old by default (`reject_old_samples_max_age`) |
| Query syntax | `{service_name="fsxn-audit"} \| json \| event_type="file.delete"` |
| Max batch | ~4 MB recommended per push |

### Honeycomb

| Aspect | Detail |
|--------|--------|
| Field indexing | All fields auto-indexed (schema-on-read) |
| Severity handling | Maps to `SeverityText` column |
| Timestamp window | Accepts events up to 7 days in the past |
| Query syntax | Column-based: `WHERE service.name = "fsxn-audit" AND event.type = "file.delete"` |
| Max batch | 5 MB per request |

### Elastic

| Aspect | Detail |
|--------|--------|
| Field indexing | Define index template with mappings for `event.type`, `svm.name` |
| Severity handling | Maps to ECS `log.level` field |
| Timestamp window | Accepts any timestamp; ILM manages retention |
| Query syntax | KQL: `service.name: "fsxn-audit" AND event.type: "file.delete"` |
| Max batch | ~10 MB recommended per bulk request |

## Validated Combinations

The following combinations have been tested end-to-end in this project:

| Source | Delivery Path | Backend | Status | Notes |
|--------|---------------|---------|--------|-------|
| Audit Logs | Direct Send | Datadog | ✅ Verified | Reference implementation |
| Audit Logs | Direct Send | Splunk | ✅ Verified | HEC endpoint |
| Audit Logs | Direct Send | Grafana | ✅ Verified | Loki push API |
| Audit Logs | OTel Collector | Datadog | ✅ Verified | otlp_http exporter |
| Audit Logs | OTel Collector | Grafana | ✅ Verified | otlp_http exporter |
| Audit Logs | OTel Collector | Honeycomb | ✅ Verified | otlp_http exporter |
| Audit Logs | OTel Collector | Multi (3) | ✅ Verified | Datadog + Grafana + Honeycomb |
| EMS / ARP | Direct Send | Datadog | ✅ Verified | Webhook → Lambda → Logs API |
| FPolicy | Direct Send | Datadog | ✅ Verified | SQS → Lambda → Logs API |
| FPolicy | OTel Collector | Datadog | ✅ Verified | SQS → Lambda → OTLP → Collector |
| EMS / ARP | OTel Collector | Grafana | 🚧 Planned | — |
| FPolicy | OTel Collector | Splunk | 🚧 Planned | — |
| Audit Logs | OTel Collector | Elastic | 🚧 Planned | — |

## Decision Guide: When to Use Which Path

```
┌─────────────────────────────────────────────┐
│ How many backends receive this telemetry?    │
└──────────────────┬──────────────────────────┘
                   │
          ┌────────┴────────┐
          │                 │
     1 backend         2+ backends
          │                 │
          ▼                 ▼
   ┌─────────────┐  ┌──────────────┐
   │ Direct Send │  │OTel Collector│
   │ (simpler)   │  │ (fan-out)    │
   └─────────────┘  └──────────────┘
```

Additional factors favoring OTel Collector:
- Backend migration planned within 12 months
- Need for centralized filtering/redaction
- Platform team provides Collector as shared service
- Compliance requires config change audit trail
