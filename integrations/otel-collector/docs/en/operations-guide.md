# OTel Collector Operations Guide

## Minimum Collector Health Checks

A production Collector deployment must monitor these signals at minimum:

| Check | Method | Healthy State | Alert Condition |
|-------|--------|---------------|-----------------|
| Collector process health | `health_check` extension on :13133 | HTTP 200 | Non-200 or timeout |
| OTLP receiver availability | HTTP GET `http://<collector>:4318` | Connection accepted | Connection refused |
| Exporter error count | Internal metric `otelcol_exporter_send_failed_log_records` | 0 | > 0 for 5 minutes |
| Exporter queue length | Internal metric `otelcol_exporter_queue_size` | < 80% capacity | > 80% capacity |
| Batch send latency | Internal metric `otelcol_exporter_send_latency` | < 5s p99 | > 10s p99 |
| Backend-specific response errors | Internal metric `otelcol_exporter_send_failed_*` per exporter | 0 | > 0 sustained |
| Last successful export timestamp | Derived from `otelcol_exporter_sent_log_records` rate | Rate > 0 | Rate = 0 for 5 minutes |

### Health Check Configuration

```yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
    path: /
    check_collector_pipeline:
      enabled: true
      exporter_failure_threshold: 5

service:
  extensions: [health_check]
  telemetry:
    metrics:
      address: 0.0.0.0:8888
      level: detailed
```

### Monitoring Script

```bash
#!/bin/bash
# Minimum health check script for cron or monitoring agent

COLLECTOR_HOST="${COLLECTOR_HOST:-localhost}"

# 1. Process health
if ! curl -sf "http://${COLLECTOR_HOST}:13133/" > /dev/null 2>&1; then
  echo "CRITICAL: Collector health check failed"
  exit 2
fi

# 2. OTLP receiver availability
if ! curl -sf -o /dev/null -w "%{http_code}" \
  "http://${COLLECTOR_HOST}:4318/v1/logs" 2>/dev/null | grep -q "405\|200"; then
  echo "WARNING: OTLP receiver not responding"
  exit 1
fi

# 3. Check internal metrics for exporter errors
FAILED=$(curl -sf "http://${COLLECTOR_HOST}:8888/metrics" 2>/dev/null \
  | grep 'otelcol_exporter_send_failed_log_records' \
  | awk '{sum += $2} END {print sum+0}')

if [ "${FAILED}" -gt 0 ]; then
  echo "WARNING: Exporter has ${FAILED} failed sends"
  exit 1
fi

echo "OK: Collector healthy"
exit 0
```

### CloudWatch Alarm for Health Check

```yaml
CollectorHealthAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: otel-collector-unhealthy
    MetricName: HealthCheckStatus
    Namespace: ECS/ContainerInsights
    Statistic: Minimum
    Period: 60
    EvaluationPeriods: 3
    Threshold: 1
    ComparisonOperator: LessThanThreshold
    AlarmActions:
      - !Ref AlertSNSTopic
```

---

## Health Checks and Monitoring

### Health Check Endpoint

The OTel Collector exposes a health check endpoint on Port 13133.

```bash
# Basic health check
curl -f http://localhost:13133/

# Example response
{"status":"Server available","upSince":"2026-05-18T14:02:03Z","uptime":"2h30m15s"}
```

### Collector Internal Metrics

The OTel Collector can expose internal metrics in Prometheus format.

```yaml
# Add to otel-collector-config.yaml
service:
  telemetry:
    metrics:
      address: 0.0.0.0:8888
      level: detailed
```

Key metrics:

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `otelcol_exporter_sent_log_records` | Successfully sent logs | — |
| `otelcol_exporter_send_failed_log_records` | Failed log sends | > 0 |
| `otelcol_receiver_accepted_log_records` | Received logs | — |
| `otelcol_receiver_refused_log_records` | Refused logs | > 0 |
| `otelcol_processor_batch_batch_send_size` | Batch size | — |

### CloudWatch Alarms

The CloudFormation template includes these alarms:

- **ErrorAlarm**: Lambda error rate exceeds threshold (5+ errors in 5 minutes)
- **ThrottleAlarm**: Lambda throttling detected
- **DLQAlarm**: Messages arriving in Dead Letter Queue

## Scaling Considerations

### Lambda Concurrency

| Log Volume | Recommended Concurrency | Memory |
|------------|------------------------|--------|
| < 100 events/min | Default (1000) | 256 MB |
| 100-1000 events/min | Default (1000) | 512 MB |
| > 1000 events/min | Set Reserved Concurrency | 1024 MB |

### OTel Collector Scaling

Docker (local/development):
- Single instance is sufficient
- CPU: 0.5 vCPU, Memory: 512 MB

ECS Fargate (production):
- Auto Scaling: horizontal scale at 70% CPU
- Min: 1 task, Max: 4 tasks
- CPU: 0.5-1 vCPU, Memory: 1-2 GB

### Batch Processor Tuning

```yaml
processors:
  batch:
    timeout: 5s          # Low latency: 1s, High throughput: 10s
    send_batch_size: 1000  # Low latency: 100, High throughput: 5000
    send_batch_max_size: 5000
```

### Processor Ordering

For production, place `memory_limiter` **before** `batch` in the processor list. This ensures memory pressure is detected before buffering additional data:

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    timeout: 5s
    send_batch_size: 1000

service:
  pipelines:
    logs:
      processors: [memory_limiter, batch]  # memory_limiter FIRST
```

The `memory_limiter` processor monitors Collector memory usage and refuses new data when the soft limit is exceeded, triggering garbage collection. This prevents OOM kills.

### Exporter Resilience: sending_queue and retry_on_failure

For production, configure each exporter with retry and queue settings:

```yaml
exporters:
  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 5000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s
```

**Key behaviors**:
- **In-memory queue** absorbs short backend outages (seconds to minutes)
- **Queue full** → new data is dropped (monitor `otelcol_exporter_enqueue_failed_log_records`)
- **Retry timeout exceeded** (`max_elapsed_time`) → oldest queued data is dropped
- **Persistent storage** (file-based queue) survives Collector restarts — configure via storage extension for production:

```yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/queue

exporters:
  otlp_http/grafana:
    sending_queue:
      storage: file_storage
```

## Failure Modes and Recovery

### Failure Pattern Summary

| Failure | Impact | Auto Recovery | Manual Action |
|---------|--------|---------------|---------------|
| OTel Collector down | Log delivery stops | Docker restart policy | Restart container |
| Backend temporary failure | Only affected backend stops | Collector retry | — |
| Backend prolonged failure | Potential log loss | Fallback to DLQ | Resend after recovery |
| Lambda timeout | Only affected batch fails | EventBridge retry | Check DLQ |
| S3 AP access failure | Cannot read logs | Lambda retry | Check IAM/network |

### Recovery Procedures

#### Restart OTel Collector

```bash
# Docker
docker restart otel-collector

# ECS Fargate
aws ecs update-service --cluster fsxn-otel --service otel-collector --force-new-deployment
```

#### Reprocess DLQ Messages

```bash
# Check DLQ message count
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages

# Reprocess messages (manually invoke Lambda)
aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 10
```

#### Backend Failure Fallback

1. Check Collector logs for send failures
2. Temporarily disable the failing backend's exporter
3. Re-enable the exporter after backend recovery
4. Resend logs from DLQ for the failure period

## Log Rotation and Retention

### CloudWatch Logs

| Log Group | Retention | Description |
|-----------|-----------|-------------|
| `/aws/lambda/fsxn-otel-integration-shipper` | 30 days | Lambda execution logs |
| `/ecs/otel-collector` | 14 days | Collector container logs |

### Collector Log Level

```yaml
service:
  telemetry:
    logs:
      level: info        # Production: info, Debug: debug
      output_paths: ["stdout"]
```

### Audit Logs (S3)

| Setting | Value | Description |
|---------|-------|-------------|
| Lifecycle rule | Glacier after 90 days | Cost optimization |
| Versioning | Enabled | Prevent accidental deletion |
| Replication | Optional | Based on DR requirements |

## Routine Maintenance

### Weekly

- [ ] Check CloudWatch alarm states
- [ ] Verify DLQ message count is 0
- [ ] Confirm Collector health check passes

### Monthly

- [ ] Check for OTel Collector image updates
- [ ] Check for Lambda runtime updates
- [ ] Cost analysis (Lambda execution time, data transfer)
- [ ] Verify log arrival rate at backends

### Quarterly

- [ ] Apply security patches
- [ ] Review IAM policies for least privilege
- [ ] Rotate Secrets Manager keys
- [ ] DR test (backend switchover)
