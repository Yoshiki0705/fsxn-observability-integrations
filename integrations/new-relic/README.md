# FSx for ONTAP New Relic Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Overview

Ships Amazon FSx for NetApp ONTAP audit logs to New Relic via the Log API. New Relic's generous free tier (100 GB/month) and unified observability platform make it suitable for teams already using New Relic for APM.

**PoC time estimate**: ~30 minutes from deploy to first queryable log in New Relic.

## Architecture

```
FSx ONTAP → S3 Bucket → S3 Access Point → EventBridge → Lambda → New Relic Log API v1
```

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-new-relic-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    NewRelicLicenseKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:nr-license-key \
    NewRelicRegion=US \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| S3AccessPointArn | ✅ | - | FSx for ONTAP S3 Access Point ARN |
| NewRelicLicenseKeySecretArn | ✅ | - | Secrets Manager ARN for New Relic License Key |
| S3BucketName | ✅ | - | S3 bucket name for EventBridge rule matching |
| NewRelicRegion | ❌ | US | New Relic region (US or EU) |
| S3KeyPrefix | ❌ | (empty) | S3 key prefix filter |
| LogLevel | ❌ | INFO | Lambda log level |
| LambdaMemorySize | ❌ | 256 | Lambda memory (MB) |
| LambdaTimeout | ❌ | 300 | Lambda timeout (seconds) |

## New Relic Regions

| Region | Log API Endpoint | Data Center |
|--------|-----------------|-------------|
| US | `https://log-api.newrelic.com/log/v1` | US |
| EU | `https://log-api.eu.newrelic.com/log/v1` | EU (Frankfurt) |

## Authentication

New Relic uses a **License Key** (40-character hex string, starts with a region identifier).

> **Note**: Use the **License Key** (also called Ingest Key), NOT the User API Key or Browser Key.

```bash
aws secretsmanager create-secret \
  --name "new-relic/fsxn-license-key" \
  --secret-string '{"license_key":"YOUR_40_CHAR_LICENSE_KEY"}' \
  --region ap-northeast-1
```

## New Relic-Side Setup

1. Log in to [New Relic](https://one.newrelic.com/)
2. Go to **API Keys** (Account dropdown → API Keys)
3. Find or create a **License Key** (INGEST - LICENSE type)
4. Copy the key
5. Store in AWS Secrets Manager (see above)

## Query Examples (NRQL)

```sql
-- Find all failed access attempts
SELECT count(*) FROM Log
WHERE source = 'fsxn-ontap' AND Result = 'Failure'
FACET UserName, ObjectName
SINCE 1 hour ago

-- Top operations by volume
SELECT count(*) FROM Log
WHERE source = 'fsxn-ontap'
FACET Operation
SINCE 1 day ago

-- Access timeline
SELECT count(*) FROM Log
WHERE source = 'fsxn-ontap'
TIMESERIES 5 minutes
SINCE 1 hour ago

-- Specific user investigation
SELECT * FROM Log
WHERE source = 'fsxn-ontap' AND UserName = 'admin@corp.local'
SINCE 1 hour ago
LIMIT 100
```

## Monitoring

- **CloudWatch Alarm**: Lambda errors > 5 in 10 minutes
- **Dead Letter Queue**: Failed events preserved for 14 days (KMS encrypted)
- **New Relic**: Create alert condition on `Log` event type with `source = 'fsxn-ontap'`

## Limits & Known Issues

- Max payload: 1MB compressed per request
- Max uncompressed: 10MB
- HTTP 202 response indicates acceptance (not guaranteed delivery)
- License Key vs User Key: only License Key works for log ingestion
- Firehose delivery is supported via New Relic's Kinesis integration

## Cost Estimate

| Monthly Log Volume | New Relic Tier |
|-------------------|---------------|
| 1 GB | Free (100 GB/month included) |
| 10 GB | Free |
| 50 GB | Free |
| 100+ GB | Paid (Data Plus: $0.35/GB beyond free tier) |

> New Relic Free Tier includes 100 GB/month of data ingest with 30-day retention. One of the most generous free tiers among observability vendors.

## Related Documents

- [Vendor Comparison](../../docs/en/vendor-comparison.md)
- [PoC Success Criteria](../../docs/en/poc-success-criteria.md)
