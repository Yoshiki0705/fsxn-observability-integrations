# FSx for ONTAP Datadog Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

## Overview

Serverless integration that ships Amazon FSx for NetApp ONTAP audit logs to Datadog via S3 Access Points and Lambda.

## Architecture

```
FSx ONTAP → S3 Bucket → S3 Access Point → EventBridge → Lambda → Datadog Logs API v2
```

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:dd-api-key \
    DatadogSite=datadoghq.com \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| S3AccessPointArn | ✅ | - | S3 Access Point ARN for audit logs |
| DatadogApiKeySecretArn | ✅ | - | Secrets Manager ARN for DD API key |
| DatadogSite | ❌ | datadoghq.com | Datadog site region |
| S3BucketName | ✅ | - | S3 bucket name for event notification |
| S3KeyPrefix | ❌ | '' | S3 key prefix filter |
| LogLevel | ❌ | INFO | Lambda log level |
| LambdaMemorySize | ❌ | 256 | Lambda memory (MB) |
| LambdaTimeout | ❌ | 300 | Lambda timeout (seconds) |

## Datadog Sites

| Site | Domain | Region |
|------|--------|--------|
| US1 | datadoghq.com | US East |
| US5 | us5.datadoghq.com | US West |
| EU1 | datadoghq.eu | EU (Frankfurt) |
| AP1 | ap1.datadoghq.com | Asia Pacific (Tokyo) |

## Tags Applied

- `source:fsxn`
- `service:ontap-audit`
- `env:<environment>`
- `s3_key:<object-key>`

## Monitoring

- CloudWatch Alarm: Lambda errors > 5 in 10 minutes
- CloudWatch Alarm: Lambda throttling detected
- CloudWatch Alarm: DLQ messages appearing
- Dead Letter Queue: Failed events preserved for 14 days
