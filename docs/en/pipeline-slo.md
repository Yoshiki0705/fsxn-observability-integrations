# Pipeline SLO Definitions

## Overview

This document defines Service Level Objectives (SLOs) for the FSx for ONTAP observability pipeline. These SLOs apply to all vendor integrations and provide measurable targets for operational health.

> **Note**: These are internal operational targets, not contractual SLAs. Adjust thresholds based on your workload requirements and vendor endpoint characteristics.

## SLO Table

| SLO | Target | Measurement Method | Alarm Threshold |
|-----|--------|-------------------|-----------------|
| **Delivery Latency** (audit logs) | < 10 minutes from file rotation to vendor ingestion | Scheduler interval (5m) + Lambda duration + vendor ingestion lag | CloudWatch: Lambda Duration p99 > 60s |
| **Delivery Latency** (EMS) | < 60 seconds from ONTAP event to vendor ingestion | API Gateway latency + Lambda duration | CloudWatch: API GW Latency p99 > 5s |
| **Delivery Latency** (FPolicy) | < 30 seconds from file operation to vendor ingestion | SQS message age + Lambda duration | CloudWatch: SQS ApproximateAgeOfOldestMessage > 30s |
| **Data Loss Rate** | < 0.01% of audit log files | DLQ message count / total scheduled invocations | CloudWatch: DLQ ApproximateNumberOfMessagesVisible > 0 |
| **Pipeline Availability** | > 99.5% (measured monthly) | Successful Lambda invocations / total invocations | CloudWatch: Lambda Errors > 5 in 10m |
| **Checkpoint Freshness** | < 15 minutes behind latest audit file | SSM Parameter Store last-modified vs current time | Custom metric: checkpoint_age_seconds > 900 |
| **DLQ Depth** | 0 (steady state) | SQS ApproximateNumberOfMessagesVisible | CloudWatch: DLQ depth > 0 for > 15m |

## SLO by Event Source

### Audit Log Poller (EventBridge Scheduler)

| Metric | Target | Rationale |
|--------|--------|-----------|
| End-to-end latency | < 10 min | 5-min schedule + processing time + vendor lag |
| Files processed per invocation | > 0 (when new files exist) | Checkpoint must advance |
| Lambda error rate | < 1% | Transient failures acceptable with retry |
| Checkpoint staleness | < 2 schedule intervals (10 min) | Indicates processing is keeping up |

### EMS Webhook (API Gateway + Lambda)

| Metric | Target | Rationale |
|--------|--------|-----------|
| API Gateway 5xx rate | < 0.1% | Near-zero server errors |
| Lambda cold start | < 3s | Acceptable for webhook path |
| End-to-end latency | < 5s | Real-time alerting requirement |

### FPolicy (ECS Fargate + SQS + Lambda)

| Metric | Target | Rationale |
|--------|--------|-----------|
| SQS message age | < 30s | Near-real-time file operation visibility |
| ECS task health | Running (steady state) | Fargate task must be healthy |
| Bridge Lambda error rate | < 1% | SQS retry handles transient failures |

## Measurement Implementation

### CloudWatch Alarms (included in templates)

Each vendor template already includes:
- Lambda Errors alarm (> 5 in 10 minutes)
- DLQ depth alarm (> 0 messages)

### Additional Recommended Alarms

```yaml
# Checkpoint staleness alarm (add to template.yaml)
CheckpointStalenessAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub "${AWS::StackName}-checkpoint-stale"
    MetricName: ParameterStoreAge
    Namespace: Custom/FSxNPipeline
    Statistic: Maximum
    Period: 300
    EvaluationPeriods: 3
    Threshold: 900
    ComparisonOperator: GreaterThanThreshold
    AlarmActions:
      - !Ref AlarmTopic

# Lambda duration P99 alarm
LambdaDurationAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub "${AWS::StackName}-duration-p99"
    MetricName: Duration
    Namespace: AWS/Lambda
    ExtendedStatistic: p99
    Period: 300
    EvaluationPeriods: 3
    Threshold: 60000
    ComparisonOperator: GreaterThanThreshold
    Dimensions:
      - Name: FunctionName
        Value: !Ref LogShipperFunction
```

## SLO Burn Rate and Error Budget

For production deployments, consider implementing SLO burn rate alerting:

| SLO | Monthly Error Budget | Fast Burn (1h window) | Slow Burn (6h window) |
|-----|---------------------|----------------------|----------------------|
| 99.5% availability | 3.6 hours downtime | > 14.4% error rate | > 2.4% error rate |
| < 0.01% data loss | ~4.3 files/month (at 1000 files/day) | > 1 DLQ message in 1h | > 3 DLQ messages in 6h |

## Go/No-Go Criteria by Production Readiness Level

### Level 1 → Level 2 (Quickstart → Operational PoC)

| Criteria | Measurement | Required |
|----------|-------------|----------|
| Audit logs arriving in vendor | Query returns results | Yes |
| Checkpoint advancing | SSM parameter updates every 5 min | Yes |
| DLQ empty for 24h | SQS metric = 0 | Yes |
| Lambda error rate < 5% | CloudWatch metric | Yes |
| Cost estimate produced | Documented | Yes |

### Level 2 → Level 3 (Operational PoC → Production Baseline)

| Criteria | Measurement | Required |
|----------|-------------|----------|
| All SLOs met for 7 consecutive days | Dashboard/metrics | Yes |
| Runbook tested (DLQ replay) | Documented test result | Yes |
| Security review completed | Checklist signed off | Yes |
| Webhook auth enabled (EMS) | Template parameter != NONE | Yes |
| Dashboard + alerts configured | Vendor-side verification | Yes |
| Cost within 20% of estimate | Billing comparison | Yes |
| Business sponsor sign-off | Documented approval | Yes |

### Level 3 → Level 4 (Production Baseline → Enterprise Pipeline)

| Criteria | Measurement | Required |
|----------|-------------|----------|
| SLOs met for 30 consecutive days | Dashboard/metrics | Yes |
| Multi-backend routing tested | OTel Collector verified | Yes |
| PII redaction rules implemented | Collector processor config | Yes |
| Compliance evidence pack complete | Governance doc signed | Yes |
| Poison-pill handling tested | Simulated bad file processed | Yes |
| DR/failover tested | Cross-region or backup path | Yes |

## Related Documents

- [Delivery Guarantee Patterns](delivery-guarantees.md)
- [Operational Guide](operational-guide.md)
- [PoC Success Criteria](poc-success-criteria.md)
- [Security Review Checklist](security-review-checklist.md)
