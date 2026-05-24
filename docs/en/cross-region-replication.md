# Cross-Region Replication for Audit Log DR

## Overview

This document describes patterns for replicating FSx for ONTAP audit log pipeline state and data across AWS regions for disaster recovery (DR) and business continuity.

> **Scope**: This covers the observability pipeline DR, not FSx for ONTAP data DR. For FSx for ONTAP file system DR, use NetApp SnapMirror or FSx for ONTAP cross-region backup.

## Why Cross-Region DR for the Pipeline?

| Scenario | Impact Without DR | With DR |
|----------|------------------|---------|
| Primary region outage | Audit logs stop flowing to vendor | Secondary region takes over |
| Vendor regional endpoint failure | Delivery fails, DLQ fills | Route to alternate vendor region |
| Compliance requirement | Single point of failure | Documented DR capability |

## Architecture Options

### Option A: Active-Passive (Recommended for Most)

Primary region processes logs normally. Secondary region has infrastructure pre-deployed but inactive (scheduler disabled). Failover is manual or automated.

```
Primary Region (ap-northeast-1)              Secondary Region (ap-southeast-1)
+----------------------------------+         +----------------------------------+
| EventBridge Scheduler (ENABLED)  |         | EventBridge Scheduler (DISABLED) |
| Lambda (processing)              |         | Lambda (standby)                 |
| SSM Checkpoint (active)          |         | SSM Checkpoint (replicated)      |
| DLQ                              |         | DLQ                              |
+----------------------------------+         +----------------------------------+
```

**Failover**: Enable secondary scheduler, Lambda resumes from replicated checkpoint.

### Option B: Active-Active (Higher Complexity)

Both regions process simultaneously using DynamoDB Global Table for shared state. Requires deduplication at the vendor side.

### Option C: Audit Log Replication Only (Simplest)

S3 Cross-Region Replication copies audit logs to secondary region. Deploy pipeline in secondary pointing at replica bucket. No state replication needed.

## Recommended: Option A Implementation

### Checkpoint Replication

```bash
#!/bin/bash
# Replicate checkpoint from primary to secondary (run every 5 min)
PRIMARY_REGION="ap-northeast-1"
SECONDARY_REGION="ap-southeast-1"
PARAM_NAME="/fsxn/<vendor>/audit-checkpoint"

CHECKPOINT=$(aws ssm get-parameter \
  --name "$PARAM_NAME" --region "$PRIMARY_REGION" \
  --query 'Parameter.Value' --output text)

aws ssm put-parameter \
  --name "$PARAM_NAME" --value "$CHECKPOINT" \
  --type String --overwrite --region "$SECONDARY_REGION"
```

### Failover Procedure

1. Detect primary region failure (CloudWatch alarm or manual)
2. Enable scheduler in secondary region
3. Secondary Lambda resumes from replicated checkpoint
4. Update ONTAP audit log destination if S3 bucket is region-specific

### Secondary Region Template

Deploy the same vendor template in the secondary region with `SchedulerState: DISABLED`:

```bash
aws cloudformation deploy \
  --template-file integrations/<vendor>/template.yaml \
  --stack-name fsxn-<vendor>-integration-dr \
  --parameter-overrides \
    S3AccessPointArn=<secondary-region-ap-arn> \
    ScheduleExpression="rate(5 minutes)" \
    SchedulerState=DISABLED \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-southeast-1
```

## RPO/RTO Targets

| Option | RPO | RTO | Monthly Cost | Complexity |
|--------|-----|-----|-------------|-----------|
| A (Active-Passive) | 5-10 min | 5-15 min | < $5 | Medium |
| B (Active-Active) | 0 | 0 | $5-20 | High |
| C (S3 Replication) | 15 min | 30-60 min | ~$0.02/GB | Low |

## DR Testing (Quarterly)

| Step | Action | Verification |
|------|--------|-------------|
| 1 | Disable primary scheduler | Primary stops processing |
| 2 | Verify checkpoint replicated | SSM in secondary matches |
| 3 | Enable secondary scheduler | Secondary starts processing |
| 4 | Confirm logs arrive in vendor | Query vendor platform |
| 5 | Re-enable primary, disable secondary | Normal operation |
| 6 | Document results | DR test evidence |

## S3 Cross-Region Replication (Option C)

```yaml
AuditLogBucket:
  Type: AWS::S3::Bucket
  Properties:
    VersioningConfiguration:
      Status: Enabled
    ReplicationConfiguration:
      Role: !GetAtt ReplicationRole.Arn
      Rules:
        - Id: AuditLogCRR
          Status: Enabled
          Prefix: audit/
          Destination:
            Bucket: !Sub arn:aws:s3:::fsxn-audit-logs-${AWS::AccountId}-dr
            StorageClass: STANDARD_IA
```

## Decision Matrix

| Requirement | Recommended Option |
|-------------|-------------------|
| Compliance checkbox (DR exists) | Option A |
| RPO < 15 min | Option A |
| RPO = 0 | Option B |
| Simplest implementation | Option C |

## Related Documents

- [Multi-Account Deployment](multi-account-deployment.md)
- [Pipeline SLO](pipeline-slo.md)
- [Delivery Guarantee Patterns](delivery-guarantees.md)
- [Compliance Evidence Pack](compliance-evidence-pack.md)
