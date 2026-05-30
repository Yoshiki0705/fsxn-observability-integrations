# FSx for ONTAP Honeycomb Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Overview

Ships Amazon FSx for NetApp ONTAP audit logs to Honeycomb via the Events Batch API. Honeycomb's high-cardinality query engine (BubbleUp, Heatmaps) is ideal for investigating file access patterns across thousands of users and paths.

**PoC time estimate**: ~30 minutes from deploy to first queryable event in Honeycomb.

> **Tip**: For multi-backend delivery (Honeycomb + other vendors), consider the [OTel Collector integration](../otel-collector/) which is verified working with Honeycomb via OTLP.

## Architecture

```
FSx for ONTAP → S3 Access Point → EventBridge → Lambda → Honeycomb Events Batch API
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
  --stack-name fsxn-honeycomb-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    HoneycombApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:honeycomb-key \
    HoneycombDataset=fsxn-audit \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| S3AccessPointArn | ✅ | - | FSx for ONTAP S3 Access Point ARN |
| HoneycombApiKeySecretArn | ✅ | - | Secrets Manager ARN for Honeycomb API key |
| S3BucketName | ✅ | - | S3 bucket name for EventBridge rule matching |
| HoneycombDataset | ❌ | fsxn-audit | Honeycomb dataset name |
| HoneycombApiUrl | ❌ | https://api.honeycomb.io | Honeycomb API base URL |
| S3KeyPrefix | ❌ | (empty) | S3 key prefix filter |
| LogLevel | ❌ | INFO | Lambda log level |
| LambdaMemorySize | ❌ | 256 | Lambda memory (MB) |
| LambdaTimeout | ❌ | 300 | Lambda timeout (seconds) |

## Authentication

Honeycomb uses **Ingest API Keys** (start with `hcaik_`). Environment keys (`hcxik_`) will NOT work.

```bash
aws secretsmanager create-secret \
  --name "honeycomb/fsxn-api-key" \
  --secret-string '{"api_key":"hcaik_01abc..."}' \
  --region ap-northeast-1
```

## Honeycomb-Side Setup

1. Log in to [Honeycomb](https://ui.honeycomb.io/)
2. Create a new dataset named `fsxn-audit` (or use existing)
3. Go to **Account** → **Team Settings** → **API Keys**
4. Create an **Ingest Key** (starts with `hcaik_`)
5. Store the key in AWS Secrets Manager (see above)

## Query Examples

```
# Find all failed file access attempts
WHERE result = "Failure" | GROUP BY user, path | COUNT

# BubbleUp: investigate spike in write operations
WHERE operation = "WriteData" | HEATMAP(duration_ms)

# Top users by file access volume
GROUP BY user | COUNT | ORDER BY COUNT DESC | LIMIT 20

# Trace file access patterns for a specific user
WHERE user = "admin@corp.local" | VISUALIZE COUNT | GROUP BY operation
```

## Batch API Format

```json
[
  {
    "time": "2026-01-15T12:00:00Z",
    "data": {
      "source": "fsxn-ontap",
      "service": "ontap-audit",
      "event_type": "4663",
      "svm": "svm-prod-01",
      "user": "admin@corp.local",
      "operation": "ReadData",
      "path": "/vol/data/file.txt",
      "result": "Success"
    }
  }
]
```

## Monitoring

- **CloudWatch Alarm**: Lambda errors > 5 in 10 minutes
- **Dead Letter Queue**: Failed events preserved for 14 days (KMS encrypted)
- **Checkpoint**: DLQ depth = 0 confirms healthy delivery

## Limits & Known Issues

- Max 100 events per batch request
- Max 5MB per request
- Ingest keys only (`hcaik_*`); environment keys (`hcxik_*`) are rejected
- Honeycomb rejects events with timestamps older than ~4 hours
- **Data residency**: Honeycomb processes data in US regions. Evaluate cross-border data transfer requirements with your compliance team before production deployment.

## Cost Estimate

| Monthly Log Volume | Honeycomb Events (est.) | Honeycomb Cost (Free Tier) |
|-------------------|------------------------|---------------------------|
| 1 GB | ~500K events | Free (20M events/month included) |
| 10 GB | ~5M events | Free |
| 100 GB | ~50M events | Paid tier required |

> Honeycomb pricing is event-based. Estimate ~500 events per MB of audit log data.

## Related Documents

- [OTel Collector Integration](../otel-collector/) — Verified Honeycomb backend via OTLP
- [Vendor Comparison](../../docs/en/vendor-comparison.md)
- [PoC Success Criteria](../../docs/en/poc-success-criteria.md)
