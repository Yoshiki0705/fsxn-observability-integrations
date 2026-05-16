# Elastic Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Setup guide for shipping FSx for ONTAP audit logs to Elasticsearch via Bulk API and visualizing in Kibana.

## Prerequisites

- Elastic Cloud or self-hosted Elasticsearch cluster
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Create Elasticsearch API Key

```bash
aws secretsmanager create-secret \
  --name "elastic/fsxn-api-key" \
  --secret-string '{"api_key":"YOUR_ENCODED_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/elastic/template.yaml \
  --stack-name fsxn-elastic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    ElasticApiKeySecretArn=arn:aws:secretsmanager:... \
    ElasticEndpoint=https://my-cluster.es.aws.found.io:9243 \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Kibana Configuration

### Index Pattern
1. Kibana → **Stack Management** → **Index Patterns**
2. Pattern: `fsxn-audit-*`, Time field: `@timestamp`

### Dashboard
- Operations pie chart: `fsxn.operation.keyword`
- Users bar chart: `user.name.keyword`
- Failed access timeline: `fsxn.result: Failure`

## Index Lifecycle Management

```json
PUT _ilm/policy/fsxn-audit-policy
{
  "policy": {
    "phases": {
      "hot": {"actions": {"rollover": {"max_age": "30d"}}},
      "delete": {"min_age": "90d", "actions": {"delete": {}}}
    }
  }
}
```
