# Sumo Logic Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Setup guide for shipping FSx for ONTAP audit logs to Sumo Logic HTTP Source.

## Prerequisites

- Sumo Logic account (Free tier: 500MB/day)
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Create HTTP Source

1. Sumo Logic → **Manage Data** → **Collection** → **Add Source**
2. Source type: **HTTP Logs & Metrics**
3. Source Category: `aws/fsxn/audit`
4. Copy the generated URL

```bash
aws secretsmanager create-secret \
  --name "sumo-logic/fsxn-http-source" \
  --secret-string '{"url":"https://endpoint1.collection.sumologic.com/receiver/v1/http/TOKEN"}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/sumo-logic/template.yaml \
  --stack-name fsxn-sumo-logic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    SumoLogicHttpSourceSecretArn=arn:aws:secretsmanager:... \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Verify

```
_sourceCategory=aws/fsxn/audit | json auto | count by Operation
```

## Troubleshooting

- **HTTP 401**: Verify HTTP Source URL
- **Payload too large**: Lambda auto-splits at 1MB
