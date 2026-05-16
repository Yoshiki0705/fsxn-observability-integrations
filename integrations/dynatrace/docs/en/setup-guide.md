# Dynatrace Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Setup guide for shipping FSx for ONTAP audit logs to Dynatrace Log Ingest API v2.

## Prerequisites

- Dynatrace environment (SaaS / Managed)
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Create Dynatrace API Token

1. Dynatrace → **Settings** → **Integration** → **Dynatrace API**
2. **Generate token** → Scopes: `logs.ingest`

```bash
aws secretsmanager create-secret \
  --name "dynatrace/fsxn-api-token" \
  --secret-string '{"api_token":"dt0c01.xxx..."}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/dynatrace/template.yaml \
  --stack-name fsxn-dynatrace-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    DynatraceApiTokenSecretArn=arn:aws:secretsmanager:... \
    DynatraceEnvUrl=https://abc12345.live.dynatrace.com \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Verify in Dynatrace

1. **Observe & Explore** → **Logs**
2. Filter: `log.source="fsxn-ontap"`
3. DQL: `fetch logs | filter log.source == "fsxn-ontap" | sort timestamp desc`

## Troubleshooting

- **HTTP 401**: Verify API Token has `logs.ingest` scope
- **Payload too large**: Lambda auto-splits at 1MB boundary
