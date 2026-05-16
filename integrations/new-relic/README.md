# FSxN New Relic Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

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

## New Relic Regions

| Region | Endpoint |
|--------|----------|
| US | `https://log-api.newrelic.com/log/v1` |
| EU | `https://log-api.eu.newrelic.com/log/v1` |

## Authentication

- **License Key** stored in Secrets Manager
- Header: `Api-Key: <license-key>`

## Limits

- Max payload: 1MB (compressed)
- Max uncompressed: 10MB
- Response: HTTP 202 on success
