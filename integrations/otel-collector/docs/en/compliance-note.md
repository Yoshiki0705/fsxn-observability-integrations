# Compliance Evidence Note: OTel Collector

🌐 [日本語](../ja/compliance-note.md) | **English** (this page)

## Collector as Distribution Layer (NOT Evidence Authority)

> **Critical distinction**: The OTel Collector is a **distribution and routing layer**, NOT the authoritative source of compliance evidence. Raw audit logs (EVTX/XML) stored in S3 remain the single source of truth.

```
┌─────────────────────────────────────────────────────────────────┐
│  Evidence Authority (Source of Truth)                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  S3 Bucket: Raw EVTX/XML audit logs                     │    │
│  │  - Immutable (versioning + Object Lock)                  │    │
│  │  - Complete (no filtering applied)                       │    │
│  │  - Timestamped by FSx for ONTAP                             │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Distribution Layer (OTel Collector)                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  - Normalized OTLP logs (search/alerting copies)         │    │
│  │  - May be filtered, sampled, or redacted                 │    │
│  │  - NOT suitable as sole compliance evidence              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Raw EVTX/XML Retention for Compliance

### Retention Requirements

| Regulation | Minimum Retention | Format | Notes |
|-----------|-------------------|--------|-------|
| SOX (J-SOX) | 7 years | Original format | Financial system access logs |
| PCI DSS | 1 year (3 months online) | Original format | Cardholder data access |
| GDPR | As needed for purpose | Original format | Right to erasure applies |
| HIPAA | 6 years | Original format | PHI access logs |
| Internal policy | Per organization | Original format | Typically 3-7 years |

### S3 Retention Configuration

```yaml
# CloudFormation: Audit log bucket with compliance retention
AuditLogBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub fsxn-audit-logs-${AWS::AccountId}
    VersioningConfiguration:
      Status: Enabled
    ObjectLockEnabled: true
    ObjectLockConfiguration:
      ObjectLockEnabled: Enabled
      Rule:
        DefaultRetention:
          Mode: COMPLIANCE
          Years: 7
    LifecycleConfiguration:
      Rules:
        - Id: TransitionToGlacier
          Status: Enabled
          Transitions:
            - StorageClass: GLACIER
              TransitionInDays: 90
        - Id: TransitionToDeepArchive
          Status: Enabled
          Transitions:
            - StorageClass: DEEP_ARCHIVE
              TransitionInDays: 365
```

## Normalized OTLP Logs as Search/Alerting Copies

The Collector delivers normalized copies to observability backends for:

| Purpose | Backend | Retention | Completeness |
|---------|---------|-----------|--------------|
| Real-time alerting | Grafana / Datadog | 30 days | May be filtered |
| Security investigation | SIEM | 1 year | Security events only |
| Operational search | Honeycomb | 60 days | May be sampled |
| Trend analysis | Any | 90 days | May be aggregated |

**These copies are NOT compliance evidence.** They are operational tools.

## Duplicate/Missing Event Handling

### Potential Causes

| Issue | Cause | Detection | Mitigation |
|-------|-------|-----------|------------|
| Duplicate events | Lambda retry on timeout | event_id deduplication | Idempotent processing |
| Missing events | Collector outage | Event count comparison | DLQ + reprocessing |
| Delayed events | Backpressure / queue full | Timestamp drift monitoring | Queue size alerting |
| Reordered events | Parallel processing | Sequence number gaps | Accept at backend |

### Event Count Reconciliation

```bash
# Compare S3 source count vs backend received count
# Source: Count objects in S3 for date range
aws s3api list-objects-v2 \
  --bucket <audit-bucket> \
  --prefix "audit/svm-prod/2026/01/" \
  --query "Contents[].Key" | jq length

# Backend: Query event count for same date range
# (vendor-specific query)
```

### Reconciliation Policy

- **Daily**: Automated count comparison (S3 objects vs backend events)
- **Weekly**: Manual review of any discrepancies > 1%
- **Monthly**: Full reconciliation report for compliance team
- **On-demand**: After any Collector outage or config change

## Per-Backend Retention Policy

| Backend | Retention | Data Scope | Deletion Policy |
|---------|-----------|------------|-----------------|
| S3 (raw) | 7 years | All events, original format | Object Lock COMPLIANCE mode |
| Security SIEM | 1 year | Security events only | Auto-expire |
| Grafana Cloud | 30 days | All events (normalized) | Auto-expire |
| Honeycomb | 60 days | All events (normalized) | Auto-expire |
| Datadog | 15 days (default) | All events (normalized) | Auto-expire |

## Routing Config Change History

All routing changes must be tracked for audit purposes:

### Required Documentation

- **Who** changed the routing (git author)
- **When** the change was made (git timestamp)
- **What** was changed (diff)
- **Why** the change was made (PR description)
- **Approval** (PR reviewer)

### Audit Query

```bash
# Full history of routing changes
git log --format="%H %ai %an %s" -- \
  'integrations/otel-collector/otel-collector-config*.yaml' \
  > routing-change-audit.log
```

## Chain of Custody Considerations

### Data Flow Documentation

```
1. FSx for ONTAP generates audit event
   → Timestamp: ONTAP system clock (NTP synced)
   → Format: EVTX or XML

2. Audit log written to S3 bucket
   → S3 object metadata: upload timestamp
   → Object Lock: immutable for retention period
   → Versioning: prevents overwrite

3. Lambda reads from S3 Access Point
   → CloudTrail: GetObject logged
   → Lambda: processing timestamp logged

4. Lambda sends OTLP to Collector
   → Network: TLS encrypted in transit
   → Collector: received timestamp in internal metrics

5. Collector exports to backends
   → Per-exporter: sent timestamp
   → Backend: ingestion timestamp
```

### Integrity Verification

| Layer | Verification Method | Frequency |
|-------|-------------------|-----------|
| S3 storage | Object Lock + versioning | Continuous |
| S3 access | CloudTrail audit | Continuous |
| Lambda processing | CloudWatch Logs | Per-invocation |
| Collector delivery | Internal metrics | Continuous |
| Backend receipt | Backend audit logs | Per-event |

## Archival Path Design

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ S3 (Standard)│────▶│ S3 (Glacier) │────▶│ S3 (Deep Archive)│
│  0-90 days   │     │  90-365 days │     │  365+ days       │
│  Online      │     │  5-12h restore│    │  12-48h restore  │
└──────────────┘     └──────────────┘     └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  OTel Collector (copies for operational use)                   │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────────────┐ │
│  │ SIEM   │  │Grafana │  │Honeycomb│  │ Archive (S3 copy) │ │
│  │ 1 year │  │ 30 days│  │ 60 days│  │ 7 years (filtered)│ │
│  └────────┘  └────────┘  └────────┘  └────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Raw logs are the authority** — never delete raw S3 logs based on backend retention
2. **Collector copies are operational** — acceptable to filter, sample, or expire
3. **Immutability at source** — Object Lock prevents tampering
4. **Restore capability** — Glacier/Deep Archive data retrievable within SLA
5. **Separation of concerns** — Compliance team owns S3 retention; platform team owns Collector routing
