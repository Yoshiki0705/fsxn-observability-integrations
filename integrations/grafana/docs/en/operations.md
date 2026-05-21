# Operations Guide — Grafana Cloud Integration

## Recommended CloudWatch Alarms

Monitor the pipeline itself, not just the logs it delivers:

| Alarm | Metric / Source | Threshold | Action |
|-------|----------------|-----------|--------|
| Scheduler DLQ depth | SQS `ApproximateNumberOfMessagesVisible` | > 0 | Investigate failed scheduled invocations |
| Lambda Errors | Lambda `Errors` | > 0 | Check CloudWatch Logs for stack traces |
| Lambda Throttles | Lambda `Throttles` | > 0 | Review reserved concurrency / backlog |
| Lambda Duration | Lambda `Duration` p95 | > 240000 ms (4 min) | Risk of timeout at 5 min; reduce MAX_KEYS_PER_RUN |
| Lambda DLQ depth | SQS `ApproximateNumberOfMessagesVisible` (Lambda DLQ) | > 0 | Processing failures after retry |
| Checkpoint age | Custom metric (see below) | > expected rotation interval | Poller may be stuck or failing silently |
| Grafana send failures | Custom metric (see below) | > 0 | OTLP Gateway may be unreachable or throttling |

## Custom Metrics (Optional)

For deeper visibility, emit custom CloudWatch metrics from the Lambda:

```python
import boto3

cloudwatch = boto3.client("cloudwatch")

def emit_metric(name: str, value: float, unit: str = "Count") -> None:
    cloudwatch.put_metric_data(
        Namespace="FSxN/Grafana",
        MetricData=[{
            "MetricName": name,
            "Value": value,
            "Unit": unit,
        }],
    )

# Examples:
# emit_metric("FilesProcessed", len(processed_keys))
# emit_metric("GrafanaSendFailures", failure_count)
# emit_metric("CheckpointAge", seconds_since_last_update, "Seconds")
```

## Poison-Pill File Handling

For the quickstart, a parse or delivery failure stops checkpoint advancement so the next run can retry safely.

For production, define a poison-pill policy:

- Retry the same object up to N times (track retry count by object key + ETag in DynamoDB)
- Move failed object metadata to a quarantine table after N failures
- Alert operators when an object exceeds retry threshold
- Optionally advance checkpoint past the poison-pill after explicit operator approval
- Log the quarantined key for later investigation

Without a poison-pill policy, one corrupted or malformed audit log file can block all subsequent files when using a high-watermark checkpoint.

## Scheduler Retry Policy Rationale

The quickstart uses:
- **MaximumRetryAttempts: 2** — surfaces persistent failures quickly
- **MaximumEventAgeInSeconds: 3600** — avoids unbounded retry storms

Increase these values only if:
- Your Grafana endpoint has known maintenance windows > 1 hour
- You have a defined duplicate-handling strategy (idempotent delivery)
- You accept that retried events may process already-checkpointed files (safe due to StartAfter)

## Failure-Path Test Coverage

The test suite covers checkpoint safety:

1. Two keys listed, first succeeds, second delivery fails → checkpoint remains at first key only
2. Grafana returns failure → Lambda raises → checkpoint does not advance
3. Empty files (0 parseable records) → treated as success, checkpoint advances
4. Scheduler re-run after failure → failed key is retried from checkpoint
5. Reserved concurrency prevents overlapping execution (CloudFormation assertion)


## Poller Tuning

Start with the quickstart defaults:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `ScheduleExpression` | `rate(5 minutes)` | Polling interval |
| `MAX_KEYS_PER_RUN` | 100 | Max files processed per invocation |
| `SAFETY_THRESHOLD_MS` | 30000 | Stop processing when <30s remaining |
| `LambdaTimeout` | 300 (5 min) | Lambda execution timeout |

### When to increase MAX_KEYS_PER_RUN

Increase only after verifying:

- Lambda p95 duration is well below the schedule interval
- Grafana OTLP send latency is stable (no 429 throttling)
- FSx S3 Access Point read throughput is not saturated
- Scheduler DLQ depth remains 0
- Checkpoint age stays within expected audit rotation interval

### When to decrease ScheduleExpression interval

Decrease (e.g., `rate(1 minute)`) when:

- Near-real-time audit visibility is required
- Audit log files are small and frequent
- Lambda duration per run is consistently < 30 seconds

### Warning signs

| Signal | Meaning | Action |
|--------|---------|--------|
| Lambda Duration p95 > 4 min | Risk of timeout | Reduce MAX_KEYS_PER_RUN |
| Scheduler DLQ messages > 0 | Invocations failing | Check Lambda errors, Grafana endpoint |
| Checkpoint not advancing | Poller stuck | Check for poison-pill file or auth failure |
| Lambda Throttles > 0 | Concurrency exhausted | Expected with ReservedConcurrency=1; check backlog |


## FSx Audit Polling Validation Checklist

Before deploying the audit log poller to production, validate:

- [ ] Audit log file naming is monotonically increasing (lexical order matches chronological order)
- [ ] Audit log rotation interval is known and documented
- [ ] Late-arriving files are not expected, or a lookback window is configured
- [ ] Average file size is measured (affects Lambda duration per file)
- [ ] FSx provisioned throughput is sufficient for polling read load
- [ ] Lambda p95 duration is below the schedule interval
- [ ] S3 Access Point file-system user has read permission on the audit log path
- [ ] S3 Access Point resource policy allows the Lambda execution role
- [ ] `StartAfter` checkpoint behavior is validated with your key naming pattern
- [ ] Scheduler DLQ alarm is configured

> **Why this matters**: The `StartAfter` high-watermark checkpoint assumes audit log keys are monotonically increasing and immutable. If files can arrive out of lexical order or be overwritten, use a DynamoDB object ledger instead.

## Ownership Matrix

For enterprise deployments, clarify operational ownership across teams:

| Area | Recommended Owner |
|------|-------------------|
| FSx audit logging configuration | Storage team |
| S3 Access Point policy | Storage / Platform |
| Lambda deployment and updates | Platform team |
| Grafana dashboards and queries | Observability team |
| Grafana alert routing and contact points | SRE / Security Operations |
| EMS webhook security | Security / Platform |
| Scheduler DLQ replay | SRE / Platform |
| Token rotation (Grafana, webhook) | Security / Platform |
| Poison-pill investigation | Storage / Platform |
| Cost monitoring (Lambda, Grafana ingest) | FinOps / Platform |

## Loki Label Cardinality Guidance

Do **not** promote high-cardinality fields to Loki labels. Keep them in the log body or structured metadata and extract at query time with `| json`.

**Fields that must NOT be labels:**
- `UserName` — unbounded user count
- `ObjectName` / `fsxn.path` — unbounded file paths
- `client.address` — unbounded IP addresses
- `event_id` — unique per event

**Fields safe as labels (low cardinality):**
- `service_name` — fixed set (`fsxn-audit`, `fsxn-ems`, `fsxn-fpolicy`)
- `severity` — small set (`alert`, `warning`, `info`)
- `operation` — bounded set (`create`, `read`, `write`, `delete`, `rename`)

> Loki indexes labels, not log content. High-cardinality labels cause index bloat, slow queries, and increased storage cost. Use `| json | UserName="admin"` instead of `{UserName="admin"}`.

Use labels for stable routing dimensions such as `service_name` and keep investigative fields in the log body or structured metadata.

## Evidence Boundary (Compliance)

For regulated environments, document the evidence boundary clearly:

| Evidence | Location | Retention |
|----------|----------|-----------|
| Audit log source of truth | FSx for ONTAP audit volume | Controlled by ONTAP retention policy |
| Analysis and alerting | Grafana Cloud Loki | Controlled by Grafana Cloud retention tier |
| Failed invocation evidence | Scheduler DLQ (SQS) | 14 days (SQS max retention) |
| Processing progress | SSM Parameter Store checkpoint | Indefinite (until deleted) |
| Lambda execution evidence | CloudWatch Logs | Configurable (default: 30 days) |
| Delivery semantics | At-least-once | Duplicates possible; dedup is app-side |

**Key principle**: Grafana Cloud is an analysis, visualization, and alerting destination — not the system of record. The FSx audit files on the ONTAP volume are the authoritative source. This pipeline delivers copies for operational visibility; it does not replace the original audit trail.


## Security Signal Tuning

Choose the right event source for each security use case:

| Signal Type | Source | Use Case | Volume |
|-------------|--------|----------|--------|
| Storage system alerts | EMS | Ransomware (ARP), quota, hardware | Low (high-confidence) |
| User/file access investigation | Audit logs | Who accessed what, when | Medium-high |
| Near-real-time file operations | FPolicy | File create/delete/rename detection | High (scope carefully) |

**Guidance**:
- Use EMS for high-confidence storage system alerts (ransomware, quota, disk failure)
- Use audit logs for user/file access investigation and compliance
- Use FPolicy for near-real-time file operation detection where latency matters
- Scope FPolicy by volume/share/path to control event volume
- Avoid sending all file operations to alerting rules without filtering — use LogQL filters to reduce noise

## Applicability Matrix

This integration pattern is designed for FSx for ONTAP. For other ONTAP environments:

| Environment | S3 Access Point Read Path | Recommended Pattern |
|-------------|--------------------------|---------------------|
| FSx for ONTAP | Yes (FSx-attached S3 Access Point) | Lambda Scheduler polling (this project) |
| On-prem ONTAP | No FSx S3 Access Point available | OTel Collector / VM-based shipper or log export |
| Cloud Volumes ONTAP | Validate available access method per cloud provider | Collector / VM-based shipper unless S3-style access path is explicitly available |
| Hybrid (FSx + on-prem) | Mixed — separate source adapters | Normalize to OTLP, aggregate in Collector |

> The S3 Access Point read path is specific to FSx for ONTAP. On-prem ONTAP and Cloud Volumes ONTAP do not have FSx S3 Access Points. For hybrid environments, use the OTel Collector (Part 5) as the aggregation layer with separate source adapters per environment.

## Troubleshooting Boundary Matrix

When investigating issues, identify the responsible layer first:

| Symptom | Check First | Likely Owner |
|---------|-------------|--------------|
| No audit files visible via S3 AP | ONTAP audit config, S3 AP permission, file-system user | NetApp / Storage |
| Lambda `AccessDenied` on GetObject | IAM policy, S3 AP resource policy, file-system user mapping | AWS / Storage |
| Scheduler DLQ messages > 0 | Scheduler logs, Lambda invocation errors | Platform / SRE |
| Lambda errors in CloudWatch | Lambda code, Grafana endpoint, credentials | Platform / Observability |
| Grafana query returns empty | OTLP delivery success, label mapping, tenant config | Observability |
| EMS events not arriving | ONTAP webhook destination config, API Gateway logs | NetApp / Security / Platform |
| FPolicy events delayed | SQS backlog, bridge Lambda errors, ECS task health | Platform / NetApp |
| Checkpoint not advancing | Poison-pill file, auth failure, Grafana 5xx | Platform (see poison-pill handling) |


## FPolicy Operational Mode Guidance

FPolicy can operate in mandatory or non-mandatory mode. Choose based on your use case:

| Mode | Behavior When External Engine Unavailable | Use Case |
|------|-------------------------------------------|----------|
| **Non-mandatory** | File operations proceed without notification | Observability-only pipelines (this project) |
| **Mandatory** | File operations blocked until engine responds | Access control / DLP enforcement |

**Recommendations for observability pipelines**:
- Use **non-mandatory** mode — the pipeline is for visibility, not access control
- Scope monitored operations to reduce event volume (e.g., create + delete + rename only)
- Scope by volume or share path where possible
- Monitor SQS backlog and bridge Lambda errors for delivery health
- Treat FPolicy events as at-least-once signals (duplicates possible on engine reconnect)
- If the ECS Fargate task restarts, update the ONTAP External Engine IP

**Volume control**: FPolicy can generate very high event volumes on busy file shares. For observability, focus on security-relevant operations (create, delete, rename) rather than all operations (open, read, write, close). Filter at the ONTAP FPolicy policy level, not in Lambda.


## OTLP Mapping

The Lambda converts parsed audit/EMS/FPolicy records to OTLP log records using this mapping:

| Source Field | OTLP Location | Rationale |
|-------------|---------------|-----------|
| `"fsxn-audit"` / `"fsxn-ems"` / `"fsxn-fpolicy"` | `resource.attributes["service.name"]` | Loki/Grafana service identity; becomes `service_name` index label |
| Signal type | `resource.attributes["fsxn.signal_type"]` | Distinguish audit / ems / fpolicy at resource level |
| SVM name | `resource.attributes["fsxn.svm.name"]` | Source SVM identification |
| Event timestamp | `log_record.time_unix_nano` | Original event time |
| ONTAP event name (EMS) | `log_record.attributes["event_name"]` | Query-time filtering |
| Audit operation | `log_record.attributes["Operation"]` | Query-time filtering |
| User name | `log_record.attributes["UserName"]` | Query-time filtering (NOT a label) |
| Object path | `log_record.attributes["ObjectName"]` | Query-time filtering (NOT a label) |
| Raw event payload | `log_record.body` | Preserve source payload for investigation |
| Severity | `log_record.severity_text` | EMS severity mapping |

### Attribute Naming Policy

- Use OTel standard attributes where applicable: `service.name`, `deployment.environment.name`, `cloud.region`
- Preserve ONTAP-native fields in `log_record.body` for full fidelity
- Add normalized custom attributes under a stable `fsxn.*` namespace:
  - `fsxn.signal_type` — audit / ems / fpolicy
  - `fsxn.svm.name` — source SVM
  - `fsxn.volume.name` — source volume (when available)
  - `fsxn.operation` — normalized operation type
  - `fsxn.result` — success / failure

When both source-native and normalized fields are present, keep the original field in the log body for forensic fidelity and add normalized `fsxn.*` attributes for cross-backend queries.

This namespace approach ensures forward compatibility if OpenTelemetry Semantic Conventions add storage-domain attributes in the future.

## Graduating to Alloy

The Lambda already emits OTLP-shaped log payloads. To move from direct send to Grafana Alloy:

1. Deploy Alloy (ECS Fargate or EC2) with an `otelcol.receiver.otlp` component
2. Change Lambda `LOKI_ENDPOINT` to point to Alloy's OTLP receiver (`http://<alloy>:4318/v1/logs`)
3. Add Alloy processors: `otelcol.processor.batch`, `otelcol.processor.attributes`, `otelcol.processor.transform`
4. Export from Alloy to Grafana Cloud OTLP endpoint via `otelcol.exporter.otlphttp`
5. Optionally add a second exporter for another backend (Datadog, S3 archive, etc.)

Benefits of the Alloy layer:
- **Batching**: Aggregate multiple Lambda invocations into efficient batches
- **Retry with persistent queue**: Survive Grafana Cloud outages without losing data
- **Transform/redaction**: Remove PII or enrich with metadata before shipping
- **Multi-backend routing**: Fan out to multiple destinations from a single pipeline
- **Resource detection**: Auto-add cloud metadata (region, account, etc.)

Because the Lambda produces standard OTLP payloads, no Lambda code changes are needed — only the destination URL changes.

Keep Lambda focused on source-specific parsing and OTLP emission. Move cross-cutting pipeline concerns such as enrichment, redaction, routing, and backend fan-out into Alloy or the OpenTelemetry Collector.

## Telemetry Pipeline SLO Examples

These are pipeline-internal SLOs, not application user-facing SLOs. They measure whether audit, EMS, and FPolicy signals arrive in Grafana within expected operational bounds.

For production, define SLOs for the pipeline itself:

| SLO | Target | Measurement |
|-----|--------|-------------|
| Freshness | 99% of audit files visible in Grafana within 2× schedule interval | Checkpoint age custom metric |
| Completeness | 99.9% of processed files have successful delivery | Grafana send failure rate |
| Replayability | 100% of Scheduler DLQ events reviewed within 1 business day | DLQ age alarm |
| Safety | 0 production audit files deleted by cleanup scripts | Cleanup script guards |
| Availability | Pipeline processes files on ≥99% of scheduled invocations | Scheduler DLQ depth = 0 |

These are starter targets. Adjust based on your organization's audit compliance requirements and operational capacity.


## Scaling Beyond a Single Poller

The single-concurrency poller (ReservedConcurrentExecutions=1) is appropriate for quickstart and low-to-medium volume workloads. For higher volume, redesign rather than simply increasing MAX_KEYS_PER_RUN:

| Approach | When to Use | Trade-off |
|----------|-------------|-----------|
| Increase MAX_KEYS_PER_RUN | Moderate volume, single prefix | Simple but bounded by Lambda timeout |
| Prefix partitioning | Multiple SVMs or audit paths | Requires stable prefix layout |
| DynamoDB object ledger | Concurrent workers needed | Higher complexity, enables dedup |
| SQS fan-out | High volume, per-object isolation | Reader lists → SQS → multiple shippers |
| Alloy / Collector | Multi-backend or enrichment needed | Compute cost, but pipeline flexibility |

**Design principles for scale**:
- Partition by stable prefixes if audit log layout supports it (e.g., per-SVM prefix)
- Replace SSM high-watermark with DynamoDB object ledger for concurrent processing
- Use SQS to fan out object processing to multiple shipper Lambdas
- Add idempotency by object key + ETag / LastModified (conditional DynamoDB writes)
- Monitor FSx S3 Access Point read throughput — it is bounded by FSx provisioned throughput
- Apply backpressure (reduce polling rate or pause) instead of increasing MAX_KEYS_PER_RUN indefinitely
- Consider Alloy / Collector when pipeline concerns (batching, retry, transform) outgrow Lambda

## Mission-Critical Workload Addendum

This pipeline is **not** a high-availability mechanism. It complements HA / DR designs by providing:

- Audit evidence for file access and administrative activity
- EMS alert visibility for ONTAP-side events (ransomware, quota, hardware)
- FPolicy-based near-real-time file operation visibility
- DLQ and checkpoint evidence for log delivery health
- Grafana dashboards and alerts for operational response

For SAP, Oracle, SQL Server, JP1, HULFT, VDI, or enterprise file service workloads on EC2 with FSx for ONTAP, combine this observability layer with workload-specific HA / DR patterns. This pipeline does not affect RTO/RPO — it provides the operational evidence and alerting that supports faster incident investigation and audit compliance.
