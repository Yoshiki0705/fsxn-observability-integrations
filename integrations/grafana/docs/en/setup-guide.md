# Grafana Cloud Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Setup guide for shipping FSx for ONTAP audit logs to Grafana Cloud Loki.

## Prerequisites

- Grafana Cloud account (Free tier available: 50GB/month)
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Prepare Grafana Cloud Credentials

1. Grafana Cloud → **My Account** → **Loki** → **Details**
2. Note Instance ID and URL
3. **Generate API Key** → Role: `MetricsPublisher`

```bash
aws secretsmanager create-secret \
  --name "grafana/fsxn-credentials" \
  --secret-string '{"instance_id":"123456","api_key":"glc_xxx..."}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/grafana/template.yaml \
  --stack-name fsxn-grafana-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    GrafanaCredentialsSecretArn=arn:aws:secretsmanager:... \
    LokiEndpoint=https://logs-prod-us-central1.grafana.net \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Verify in Grafana

### Explore → Loki

```logql
{job="fsxn-audit"} | json
{job="fsxn-audit", svm="svm-prod-01"} | json | Result="Failure"
```

### Dashboard Panels

- Log volume: `rate({job="fsxn-audit"}[5m])`
- Operations breakdown: `sum by (Operation) (count_over_time({job="fsxn-audit"} | json [1h]))`
- Failed access: `{job="fsxn-audit"} | json | Result="Failure"`

## Troubleshooting

- **HTTP 401**: Verify Instance ID / API Key
- **Out of order entries**: Loki requires ascending timestamps
- **Rate limit**: Free tier allows 4MB/min
