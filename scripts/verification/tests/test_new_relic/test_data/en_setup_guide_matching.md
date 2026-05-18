# Setup Guide

## Prerequisites

- AWS Account
- New Relic Account (free tier 100GB/month)

## Deployment Steps

### Step 1: Prepare New Relic License Key

Obtain the License Key from the New Relic console.

```bash
aws secretsmanager create-secret \
  --name fsxn-new-relic-license-key \
  --secret-string YOUR_LICENSE_KEY \
  --region ap-northeast-1
```

### Step 2: CloudFormation Deployment

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointArn` | S3 AP ARN | - |
| `NewRelicLicenseKeySecretArn` | License Key Secret ARN | - |
| `NewRelicRegion` | New Relic region | `US` |

```bash
aws cloudformation deploy \
  --template-file integrations/new-relic/template.yaml \
  --stack-name fsxn-new-relic-integration \
  --capabilities CAPABILITY_IAM
```

## Verification

Send a test event to verify the integration works.

```json
{
  "Records": [
    {
      "s3": {
        "bucket": {"name": "fsxn-audit-logs"},
        "object": {"key": "audit/svm-prod/2026/01/15/audit.json"}
      }
    }
  ]
}
```

## NRQL Query Examples

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago
```
