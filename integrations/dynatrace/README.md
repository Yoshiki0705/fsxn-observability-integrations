# FSx for ONTAP Dynatrace Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Overview

Ships Amazon FSx for NetApp ONTAP audit logs to Dynatrace via the Log Ingest API v2. Dynatrace's AI-powered root cause analysis (Davis AI) can correlate file access anomalies with application performance issues.

**PoC time estimate**: ~30 minutes from deploy to first queryable log in Dynatrace.

## Architecture

```
FSx for ONTAP → S3 Access Point → EventBridge → Lambda → Dynatrace Log Ingest API v2
```

## Prerequisites

See [Prerequisites Guide](../../docs/en/prerequisites.md) for ONTAP audit logging setup and S3 Access Point configuration.

## Event Source Templates

| Event Source | Template | Description |
|-------------|----------|-------------|
| Audit Logs (S3 AP polling) | `template.yaml` | Primary audit log shipper |
| EMS Webhooks | `template-ems.yaml` | ONTAP EMS events via API Gateway |
| FPolicy (file operations) | `template-fpolicy.yaml` | Real-time file operation events |

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-dynatrace-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    DynatraceApiTokenSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:dynatrace-token \
    DynatraceEnvUrl=https://abc12345.live.dynatrace.com \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| S3AccessPointArn | ✅ | - | FSx for ONTAP S3 Access Point ARN |
| DynatraceApiTokenSecretArn | ✅ | - | Secrets Manager ARN for Dynatrace API token |
| DynatraceEnvUrl | ✅ | - | Dynatrace environment URL |
| S3BucketName | ✅ | - | S3 bucket name for EventBridge rule matching |
| S3KeyPrefix | ❌ | (empty) | S3 key prefix filter |
| LogLevel | ❌ | INFO | Lambda log level |
| LambdaMemorySize | ❌ | 256 | Lambda memory (MB) |
| LambdaTimeout | ❌ | 300 | Lambda timeout (seconds) |

## Authentication

Dynatrace uses **API Tokens** with the `logs.ingest` scope.

```bash
aws secretsmanager create-secret \
  --name "dynatrace/fsxn-api-token" \
  --secret-string '{"api_token":"dt0c01.XXXXXXXX.YYYYYYYY"}' \
  --region ap-northeast-1
```

## Dynatrace-Side Setup

1. Log in to your Dynatrace environment
2. Go to **Access Tokens** (Settings → Integration → Access tokens)
3. Create a new token with scope: **`logs.ingest`**
4. Copy the generated token (format: `dt0c01.XXXXXXXX.YYYYYYYY`)
5. Store in AWS Secrets Manager (see above)

### Environment URL Format

| Deployment Type | URL Format |
|----------------|------------|
| SaaS | `https://<env-id>.live.dynatrace.com` |
| Managed | `https://<your-domain>/e/<env-id>` |
| ActiveGate | `https://<activegate-host>:9999/e/<env-id>` |

## Query Examples (DQL)

```dql
// Find all failed file access attempts
fetch logs
| filter log.source == "fsxn-ontap" and fsxn.operation != ""
| filter contains(content, "Failure")
| summarize count(), by: {fsxn.user, fsxn.path}

// Top operations by volume
fetch logs
| filter log.source == "fsxn-ontap"
| summarize count(), by: {fsxn.operation}
| sort count() desc

// Access timeline for a specific SVM
fetch logs
| filter fsxn.svm == "svm-prod-01"
| makeTimeseries count(), interval: 5m
```

## Log Entry Format

```json
{
  "content": "{\"EventID\":\"4663\",\"UserName\":\"admin@corp.local\",...}",
  "log.source": "fsxn-ontap",
  "dt.source_entity": "CUSTOM_DEVICE-fsxn-svm-prod-01",
  "timestamp": "2026-01-15T12:00:00Z",
  "severity": "info",
  "fsxn.svm": "svm-prod-01",
  "fsxn.operation": "ReadData",
  "fsxn.user": "admin@corp.local",
  "fsxn.path": "/vol/data/file.txt",
  "fsxn.s3_key": "audit/2026/01/15/audit-001.json"
}
```

## Monitoring

- **CloudWatch Alarm**: Lambda errors > 5 in 10 minutes
- **Dead Letter Queue**: Failed events preserved for 14 days (KMS encrypted)
- **Dynatrace**: Monitor custom device entity for ingestion health

## Limits & Known Issues

- Max 1MB per request
- API token requires `logs.ingest` scope (not `ReadConfig` or `WriteConfig`)
- Dynatrace returns HTTP 204 on success (not 200)
- Log entries older than 24 hours may be rejected depending on environment settings
- Firehose delivery is supported but requires Dynatrace ActiveGate
- **Data residency**: Dynatrace SaaS environments are region-specific. For Managed or ActiveGate deployments, data stays in your infrastructure. Evaluate cross-border data transfer requirements with your compliance team.

## Cost Estimate

| Monthly Log Volume | DDU Consumption (est.) | Notes |
|-------------------|----------------------|-------|
| 1 GB | ~1 DDU/day | Minimal cost |
| 10 GB | ~10 DDU/day | Within most license allocations |
| 100 GB | ~100 DDU/day | Review DDU allocation with Dynatrace |

> Dynatrace pricing is based on Davis Data Units (DDU). Log ingestion consumes approximately 1 DDU per GB ingested. Check your license allocation.

## Related Documents

- [Vendor Comparison](../../docs/en/vendor-comparison.md)
- [PoC Success Criteria](../../docs/en/poc-success-criteria.md)
