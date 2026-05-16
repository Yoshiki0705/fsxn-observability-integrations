# New Relic Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Setup guide for shipping FSx for ONTAP audit logs to New Relic Logs.

## Prerequisites

- AWS Account (FSx ONTAP running)
- New Relic Account (Logs enabled)
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Prepare New Relic License Key

1. New Relic → **API Keys** → **Create a key**
2. Key type: `INGEST - LICENSE`
3. Copy the generated License Key

```bash
aws secretsmanager create-secret \
  --name "new-relic/fsxn-license-key" \
  --secret-string '{"license_key":"YOUR_LICENSE_KEY"}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/new-relic/template.yaml \
  --stack-name fsxn-new-relic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    NewRelicLicenseKeySecretArn=arn:aws:secretsmanager:... \
    NewRelicRegion=US \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: New Relic Configuration

### Parsing Rule
1. **Logs** → **Parsing** → **Create parsing rule**
2. NRQL: `SELECT * FROM Log WHERE source='fsxn-ontap'`

### Alert Condition
```sql
SELECT count(*) FROM Log
WHERE source = 'fsxn-ontap' AND attributes.result = 'Failure'
FACET attributes.user
```

## Step 4: Verify

Upload test file and check New Relic Logs UI → `source:fsxn-ontap`.

## Troubleshooting

- **HTTP 403**: Verify License Key
- **HTTP 429**: Rate limited — reduce Lambda concurrency
- **No logs**: Check Lambda errors in CloudWatch Logs
