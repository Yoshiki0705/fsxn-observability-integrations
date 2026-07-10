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

## Forensic Investigation (Kibana Discover/Lens)

> 🔍 For a user/IP/path-centric investigation workflow (who accessed what, from where, doing what — similar to DII Storage Workload Security's Forensics dashboards), the [Normalized Event Schema](../../../docs/en/normalized-event-schema.md) already maps ONTAP audit and FPolicy fields to ECS (`user.name`, `source.ip`, `file.path`, `event.action`), so no custom mapping is required. Build the following in Kibana:

### Saved Searches (KQL)

| Investigation View | KQL Query | Equivalent DII SWS View |
|---------------------|-----------|--------------------------|
| User Overview | `user.name: "<value>"` | Forensic User Overview |
| All Activity | `event.dataset: "fsxn"` (no filter, sorted by `@timestamp` descending) | Forensics - All Activity |
| IP-Centric Drill-Down | `source.ip: "<value>"` | Forensic User Activity Data |
| Entity / File History | `file.path: "<value>"` | Forensic Entities Page |

Save each as a Kibana **Saved Search** with a descriptive name (e.g., `fsxn-forensics-user-overview`) so investigators can select the right view from Discover without rebuilding the query.

### Lens Visualization

Add a **Lens** bar chart breaking down `event.action` (operation type) for the currently filtered saved search — this surfaces anomalous action mixes (e.g., a spike in delete operations) the same way DII SWS's Forensics dashboards highlight action distribution per user/entity.

### Export

Discover's **Share → CSV Reports** (or **Generate CSV** in newer Kibana versions) exports the current filtered view, scoped to whatever time range you've selected — equivalent to DII SWS's 31-day filtered CSV export, without the fixed 31-day ceiling (retention is governed by your ILM policy above instead).

See [DII Capability Map](../../../docs/en/dii-capability-map.md) for the full phase-by-phase comparison this implements, including known data-source caveats (FPolicy vs audit log coverage gaps, PII handling via the [Data Classification Guide](../../../docs/en/data-classification.md)).
