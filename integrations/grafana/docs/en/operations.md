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
