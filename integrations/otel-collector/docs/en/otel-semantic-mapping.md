# OTel Semantic Mapping Guide

🌐 [日本語](../ja/otel-semantic-mapping.md) | **English** (this page)

## Attribute Classification

### Standard / Well-Known Attributes

| Attribute | Source | OTel Semantic Convention | Notes |
|-----------|--------|------------------------|-------|
| `service.name` | Config | [Service resource](https://opentelemetry.io/docs/specs/semconv/resource/#service) | Standard |
| `cloud.provider` | Config | [Cloud resource](https://opentelemetry.io/docs/specs/semconv/resource/cloud/) | Standard (`aws`) |
| `user.name` | FSx for ONTAP `UserName` | General convention | Widely understood |
| `client.address` | FSx for ONTAP `ClientIP` | [Client attributes](https://opentelemetry.io/docs/specs/semconv/attributes-registry/client/) | Standard |

### Project-Specific Attributes (fsxn.* namespace)

| Attribute | Source | Why Not Standard | Notes |
|-----------|--------|-----------------|-------|
| `fsxn.operation` | FSx for ONTAP `Operation` | ONTAP-specific operation names | Could map to `event.action` in future |
| `fsxn.path` | FSx for ONTAP `ObjectName` | ONTAP volume path semantics differ from `file.path` | Volume-relative path |
| `fsxn.result` | FSx for ONTAP `Result` | ONTAP-specific result values | Drives severity mapping |
| `fsxn.svm` | FSx for ONTAP `SVMName` | No standard for storage VM | NetApp-specific concept |
| `event.type` | FSx for ONTAP `EventID` | Currently holds numeric ID (4663) | Consider `event.id` or `fsxn.event_id` in future |
| `cloud.platform` | Config | `aws_fsx` is not in standard enum | Project-specific marker |

## Schema Evolution Considerations

The current mapping prioritizes:
1. **Readability** — attribute names are self-explanatory
2. **Backend compatibility** — works across Datadog, Grafana, Honeycomb
3. **Stability** — existing queries won't break

Future revisions may consider:
- `event.type` → `event.id` (numeric Windows Event ID)
- `fsxn.operation` → dual-emit with `event.action`
- `fsxn.path` → dual-emit with `file.path` (where semantics align)
- `cloud.platform` → custom resource attribute outside standard enum

> **Important**: Any schema change requires updating all Lambda handlers, test data, backend queries, and documentation simultaneously. Use a versioned migration approach.

## What OTLP Does Not Solve

OTLP standardizes the wire format between producers and the Collector. It does NOT guarantee:
- Identical field indexing across backends
- Same query syntax across backends
- Equivalent retention policies
- Matching severity/status visualization
- Automatic facet/field creation

Each backend interprets OTLP attributes according to its own data model. Validate per-backend behavior during PoC (see [PoC Checklist](poc-checklist.md)).

## OpenTelemetry Is Not a Backend

OpenTelemetry defines:
- APIs and SDKs for telemetry generation
- OTLP protocol for telemetry transport
- Collector for telemetry processing and export
- Semantic conventions for attribute naming

OpenTelemetry does NOT provide:
- Storage or indexing
- Visualization or dashboards
- Alerting or incident management
- Long-term retention

These are the responsibility of backends (Datadog, Grafana Cloud, Honeycomb, Splunk, etc.).
