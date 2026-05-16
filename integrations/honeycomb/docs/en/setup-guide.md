# Honeycomb Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Setup guide for shipping FSx for ONTAP audit logs to Honeycomb Events API.

## Prerequisites

- Honeycomb account
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Prepare Honeycomb API Key

1. Honeycomb → **Team Settings** → **API Keys**
2. **Create API Key** → Permissions: `Send Events`
3. Dataset: `fsxn-audit` (auto-created on first event)

```bash
aws secretsmanager create-secret \
  --name "honeycomb/fsxn-api-key" \
  --secret-string '{"api_key":"YOUR_HONEYCOMB_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/honeycomb/template.yaml \
  --stack-name fsxn-honeycomb-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    HoneycombApiKeySecretArn=arn:aws:secretsmanager:... \
    HoneycombDataset=fsxn-audit \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Verify in Honeycomb

1. Dataset: `fsxn-audit`
2. Query: `GROUP BY operation, VISUALIZE COUNT`
3. Filter: `result = Failure`

## Why Honeycomb

- Excellent for high-cardinality data exploration
- BubbleUp auto-detects anomalous patterns
- SLO tracking for file access success rates
