# FPolicy Production Architecture Patterns

## Overview

This document describes production architecture patterns for the FPolicy file activity pipeline. The [Part 4 blog article](https://dev.to/aws-builders/fpolicy-file-activity-pipeline-ontap-to-datadog-via-ecs-fargate) validates the end-to-end path with a single Fargate task. Production deployments require additional design for HA, IP stability, and failure recovery.

## Pattern 1: Single Fargate Task (Validation)

```
ONTAP FPolicy → Fargate Task (single) → SQS → Lambda → Vendor
```

- **Use case**: PoC, development, low-volume monitoring
- **Pros**: Simplest deployment, lowest cost (~$14/month AWS-side)
- **Cons**: Single point of failure, IP changes on restart, ~2 minute recovery gap
- **IP update**: Helper script or manual (`fpolicy-update-engine-ip.sh --auto`)

## Pattern 2: Primary/Secondary FPolicy Servers

ONTAP external engine supports `primary-servers` and `secondary-servers` parameters. When the primary server is unreachable, ONTAP fails over to secondary servers.

```
ONTAP FPolicy
  ├─ primary-servers: [Fargate Task A IP]
  └─ secondary-servers: [Fargate Task B IP]
```

- **Use case**: Production with HA requirement
- **Pros**: Automatic failover by ONTAP, no event loss during single task restart
- **Cons**: Two Fargate tasks running (~$28/month), IP update needed for both
- **Design notes**:
  - Deploy two ECS services in different AZs
  - ONTAP handles failover natively
  - Both tasks write to the same SQS queue
  - Lambda deduplication may be needed (use `event_id`)

### ONTAP Configuration

```
vserver fpolicy policy external-engine create -vserver <svm-name> \
  -engine-name fpolicy_aws_engine \
  -primary-servers <task-a-ip> \
  -secondary-servers <task-b-ip> \
  -port 9898 \
  -extern-engine-type asynchronous \
  -ssl-option no-auth
```

## Pattern 3: Auto-Update with State Reconciliation

Instead of manual IP updates, use an EventBridge-triggered Lambda that reconciles the desired state (ONTAP engine IP = current healthy task IP).

```
ECS Task State Change (RUNNING)
  → EventBridge Rule
    → IP Reconciliation Lambda
      → Compare current task IP with ONTAP engine primary-servers
      → Update only when drift detected
      → Emit success/failure CloudWatch metric
```

- **Use case**: Production with automated recovery
- **Pros**: No manual intervention, self-healing
- **Cons**: Requires ONTAP REST API access from Lambda (VPC + NAT or VPC-internal)
- **Prerequisites**:
  - Network reachability to ONTAP management endpoint
  - ONTAP credentials in Secrets Manager with permission to modify FPolicy external engine
  - Lambda in VPC with NAT Gateway (for ONTAP REST API access)

## Pattern 4: Multi-AZ Placement

For AZ-level resilience, deploy Fargate tasks across multiple AZs.

| Component | AZ Resilience | Notes |
|-----------|--------------|-------|
| Fargate Task | Single AZ per task | Use spread placement or multiple services |
| SQS Queue | Multi-AZ (managed) | No action needed |
| Lambda | Multi-AZ (managed) | No action needed |
| ONTAP SVM | Depends on FSx deployment type | Single-AZ or Multi-AZ file system |

### Failure Mode Matrix

| Failure | Impact | Recovery |
|---------|--------|----------|
| Fargate task crash | Events lost during restart (~2 min) | ECS auto-restart + IP update |
| AZ failure (single-AZ FSx) | Full pipeline down | FSx failover + new Fargate task |
| AZ failure (multi-AZ FSx) | Fargate task in failed AZ lost | ONTAP failover to secondary server |
| ONTAP planned maintenance | Brief disconnection | ONTAP reconnects after maintenance |
| Lambda throttling | Events buffer in SQS | Auto-scales, no data loss |
| Datadog API outage | Events buffer in SQS | Lambda retries with backoff |

## Planned Maintenance Runbook

1. **Before maintenance**: Verify SQS queue is empty, confirm KeepAlive is healthy
2. **During maintenance**: Events buffer in SQS if Fargate is affected
3. **After maintenance**: Verify ONTAP reconnects (check KeepAlive in ECS logs)
4. **If IP changed**: Run `fpolicy-update-engine-ip.sh --auto` or wait for auto-reconciliation

## References

- [NetApp FPolicy external engine documentation](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-external-engine-task.html)
- [AWS Fargate documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [FPolicy persistent store (ONTAP 9.14.1+)](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)
