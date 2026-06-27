# FSx for ONTAP Sumo Logic Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Overview

Ships Amazon FSx for NetApp ONTAP audit logs to Sumo Logic via HTTP Source. Sumo Logic's free tier (1.25 credits/day under Flex model) makes it accessible for initial validation and small-scale deployments.

**PoC time estimate**: ~30 minutes from deploy to first queryable log in Sumo Logic.

## Architecture

```
FSx for ONTAP → S3 Access Point → EventBridge → Lambda → Sumo Logic HTTP Source
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
  --stack-name fsxn-sumo-logic-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    SumoLogicHttpSourceSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:sumo-http-source \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| S3AccessPointArn | ✅ | - | FSx for ONTAP S3 Access Point ARN |
| SumoLogicHttpSourceSecretArn | ✅ | - | Secrets Manager ARN for HTTP Source URL |
| S3BucketName | ✅ | - | S3 bucket name for EventBridge rule matching |
| S3KeyPrefix | ❌ | (empty) | S3 key prefix filter |
| SourceCategory | ❌ | aws/fsxn/audit | Sumo Logic source category |
| SourceName | ❌ | fsxn-ontap-audit | Sumo Logic source name |
| LogLevel | ❌ | INFO | Lambda log level |
| LambdaMemorySize | ❌ | 256 | Lambda memory (MB) |
| LambdaTimeout | ❌ | 300 | Lambda timeout (seconds) |

## Authentication

Sumo Logic uses HTTP Source URLs with **embedded authentication tokens**. The full URL is stored in Secrets Manager.

> ⚠️ **Security Note**: The HTTP Source URL contains the authentication token. Treat it as a secret — never log it, expose it in environment variables, or commit it to source control.

```bash
aws secretsmanager create-secret \
  --name "sumo-logic/fsxn-http-source" \
  --secret-string '{"url":"https://endpoint1.collection.sumologic.com/receiver/v1/http/YOUR_TOKEN"}' \
  --region ap-northeast-1
```

## Sumo Logic-Side Setup

1. Log in to [Sumo Logic](https://service.sumologic.com/)
2. Go to **Manage Data** → **Collection** → **Add Source**
3. Select **HTTP Logs & Metrics Source**
4. Configure:
   - Name: `fsxn-ontap-audit`
   - Source Category: `aws/fsxn/audit`
   - Timestamp Parsing: Auto-detect
5. Copy the generated HTTP Source URL
6. Store in AWS Secrets Manager (see above)

## Query Examples

```sql
-- Find all failed access attempts
_sourceCategory=aws/fsxn/audit
| json "Result", "UserName", "ObjectName"
| where Result = "Failure"
| count by UserName, ObjectName

-- Top operations by volume
_sourceCategory=aws/fsxn/audit
| json "Operation"
| count by Operation
| sort by _count desc

-- Access pattern timeline
_sourceCategory=aws/fsxn/audit
| json "Operation", "UserName"
| timeslice 5m
| count by _timeslice, Operation
```

## Sumo Logic Headers

Lambda sends the following metadata headers with each request:

| Header | Value | Description |
|--------|-------|-------------|
| `X-Sumo-Category` | `aws/fsxn/audit` | Source category for search |
| `X-Sumo-Name` | `fsxn-ontap-audit` | Source name |
| `X-Sumo-Host` | `fsxn-ontap` | Host identifier |

## Monitoring

- **CloudWatch Alarm**: Lambda errors > 5 in 10 minutes
- **Dead Letter Queue**: Failed events preserved for 14 days (KMS encrypted)
- **Sumo Logic Health Events**: Monitor HTTP Source ingestion rate

## Limits & Known Issues

- Max 1MB per request (newline-delimited JSON)
- HTTP Source URL contains embedded auth token — rotate by creating a new source
- No built-in Firehose support — Lambda direct delivery only
- Sumo Logic Free Tier: 1.25 credits/day (logs, metrics, traces combined), 7-day retention
- **Data residency**: Sumo Logic deployments are region-specific (US, EU, AU, JP, etc.). Select the deployment matching your data residency requirements. Evaluate cross-border data transfer with your compliance team.

## Cost Estimate

| Monthly Log Volume | Daily Average | Sumo Logic Tier |
|-------------------|---------------|-----------------|
| 1 GB | ~33 MB/day | Free (1.25 credits/day) |
| 10 GB | ~333 MB/day | Free |
| 15+ GB | 500+ MB/day | Paid tier required |

> Sumo Logic Free Tier provides 1.25 credits/day (Cloud Flex Credits model) with 7-day log retention and up to 3 users. Credits cover logs, metrics, and traces in any combination.

## Related Documents

- [Vendor Comparison](../../docs/en/vendor-comparison.md)
- [PoC Success Criteria](../../docs/en/poc-success-criteria.md)
