# PoC Success Criteria

Common success criteria for all FSx for ONTAP observability integrations. Use this document to define clear exit conditions for each stage of validation.

## Minimum Success (Level 1)

The absolute minimum to prove the pipeline works end-to-end:

- [ ] One audit log file is read from the S3 Access Point
- [ ] One log record arrives in the observability backend and is queryable
- [ ] SSM checkpoint advances only after successful delivery
- [ ] DLQ remains empty (no failed deliveries)
- [ ] Deployment script (`aws cloudformation deploy`) completes without errors
- [ ] Cleanup script (`aws cloudformation delete-stack`) removes all resources cleanly

### Verification Commands

```bash
# Confirm checkpoint advanced
aws ssm get-parameter \
  --name /fsxn/observability/checkpoint \
  --query 'Parameter.Value' --output text

# Confirm DLQ is empty
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages'

# Query backend (example: Datadog)
# source:fsxn earliest:-15m
```

## Operational Success (Level 2)

Proves the pipeline is observable and operable:

- [ ] Lambda errors and throttles are monitored (CloudWatch Alarm configured)
- [ ] DLQ depth alarm is configured and tested
- [ ] Checkpoint age metric is available (staleness detection)
- [ ] Replay procedure is documented and tested (manual DLQ drain)
- [ ] Secrets rotation behavior is tested (new token picked up on next cold start)
- [ ] Cost estimate is produced for expected log volume
- [ ] Dashboard shows log volume, delivery latency, and error rate

### Key Metrics to Track

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| Lambda Errors | CloudWatch | > 0 for 2 consecutive periods |
| DLQ Depth | SQS ApproximateNumberOfMessages | > 0 |
| Checkpoint Age | Custom metric or Scheduler failure | > 2× polling interval |
| Delivery Latency | Custom metric (file timestamp → backend queryable) | > 5 minutes |

## Production Readiness Gate (Level 3)

Exit criteria before production deployment:

- [ ] Webhook authentication is enabled (API key, IAM, or WAF)
- [ ] Delivery guarantee level is selected and documented (at-least-once vs exactly-once)
- [ ] DynamoDB object ledger decision is made (needed for exactly-once)
- [ ] OTel Collector / Grafana Alloy graduation decision is made
- [ ] Retention and compliance requirements are approved by security team
- [ ] Security review checklist is completed
- [ ] Governance and compliance review is completed
- [ ] Load test with expected peak volume is passed
- [ ] Runbook covers: delivery failure, checkpoint reset, token rotation, DLQ replay

### Production Readiness Review Questions

1. What is the expected daily log volume (GB/day)?
2. What is the acceptable delivery latency (seconds/minutes)?
3. Is cross-border data transfer acceptable for the chosen backend?
4. Who owns the pipeline operationally (monitoring, escalation, maintenance)?
5. What is the token rotation schedule?
6. Is the DLQ replay procedure approved by security?

## EMS / FPolicy Additional Criteria

For integrations that include EMS webhook or FPolicy event paths:

### EMS Webhook
- [ ] API Gateway endpoint is secured (not publicly unauthenticated)
- [ ] ONTAP EMS destination is configured and sending events
- [ ] At least one EMS event (e.g., `arw.volume.state`) arrives in backend
- [ ] Webhook latency is < 30 seconds (ONTAP → backend queryable)

### FPolicy
- [ ] ECS Fargate task is running and receiving ONTAP KeepAlive messages
- [ ] At least one file operation event arrives in backend via SQS → Lambda
- [ ] ONTAP External Engine IP is updated after Fargate task restart
- [ ] FPolicy latency is < 30 seconds (file operation → backend queryable)

## Multi-Backend Criteria (OTel Collector / Alloy)

For OTel Collector or Grafana Alloy deployments:

- [ ] Single Lambda emits OTLP to Collector/Alloy
- [ ] Collector/Alloy routes to all configured backends simultaneously
- [ ] Each backend receives the same log records (parity check)
- [ ] Collector health endpoint is monitored
- [ ] Persistent queue is configured for reliability
- [ ] Memory limiter prevents OOM under load

## Related Documents

- [Governance and Compliance](governance-and-compliance.md)
- [Security Review Checklist](security-review-checklist.md)
- [Delivery Guarantee Patterns](delivery-guarantees.md)
- [Operational Guide](operational-guide.md)
- [Production Readiness Levels (README)](../../README.md#production-readiness-levels--本番準備レベル)
