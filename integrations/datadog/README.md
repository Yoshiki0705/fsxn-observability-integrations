# FSx for ONTAP Datadog Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Overview

EC2-free integration that ships Amazon FSx for NetApp ONTAP audit logs to Datadog. Lambda reads audit log files from the FSx volume via an FSx for ONTAP S3 Access Point and ships them to the Datadog Logs API v2.

**PoC time estimate**: ~30 minutes from deploy to first queryable log in Datadog.

> ⚠️ Datadog has no free tier for log ingestion. PoC will incur costs (~$0.10/GB ingested). Consider using the [OTel Collector integration](../otel-collector/) with a free-tier backend (Grafana/Honeycomb) for initial validation if budget is a concern.

## Architecture

```
FSx ONTAP audit volume → FSx ONTAP S3 Access Point → EventBridge Scheduler → Lambda → Datadog Logs API v2
```

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:dd-api-key \
    DatadogSite=ap1.datadoghq.com \
  --capabilities CAPABILITY_NAMED_IAM
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| FsxS3AccessPointArn | ✅ | - | FSx for ONTAP S3 Access Point ARN (attached to audit volume) |
| DatadogApiKeySecretArn | ✅ | - | Secrets Manager ARN for DD API key |
| DatadogSite | ❌ | ap1.datadoghq.com | Datadog site region |
| AuditLogPrefix | ❌ | audit/ | Key prefix for audit log files |
| ScheduleRate | ❌ | rate(5 minutes) | How often to check for new audit logs |
| LogLevel | ❌ | INFO | Lambda log level |
| LambdaMemorySize | ❌ | 256 | Lambda memory (MB) |
| LambdaTimeout | ❌ | 300 | Lambda timeout (seconds) |
| VpcEnabled | ❌ | false | Enable VPC config (requires NAT Gateway for S3 AP access) |

## Datadog Sites

| Site | Domain | Region |
|------|--------|--------|
| US1 | datadoghq.com | US East |
| US3 | us3.datadoghq.com | US |
| US5 | us5.datadoghq.com | US West |
| EU1 | datadoghq.eu | EU (Frankfurt) |
| AP1 | ap1.datadoghq.com | Asia Pacific (Tokyo) |
| AP2 | ap2.datadoghq.com | Asia Pacific |
| US1-FED | ddog-gov.com | US Government |

## Tags Applied

- `source:fsxn`
- `service:ontap-audit`
- `env:<environment>`

## Monitoring

- CloudWatch Alarm: Lambda errors > 5 in 10 minutes
- CloudWatch Alarm: Lambda throttling detected
- CloudWatch Alarm: DLQ messages appearing
- Dead Letter Queue: Failed events preserved for 14 days

## Important Notes

- **FSx ONTAP S3 APs do NOT support S3 Event Notifications.** Lambda is invoked on a schedule (EventBridge Scheduler) and uses checkpointing to process only newly rotated files.
- **Internet-origin S3 APs** timed out with only a Gateway Endpoint in our environment. If Lambda is in a VPC, use NAT Gateway or create a VPC-origin AP.
- Audit log format: EVTX or XML (configured via `vserver audit create -format {evtx|xml}`)
