# OTel Collector Operations Guide

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
