# Splunk Serverless Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Serverless integration shipping FSx for ONTAP audit logs to Splunk via HEC.

> **Difference from existing pattern**: Replaces the [EC2-based approach](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/) (syslog-ng + Universal Forwarder) with fully serverless architecture.

## Prerequisites

- Splunk Enterprise / Splunk Cloud (HEC enabled)
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Create Splunk HEC Token

1. Splunk Web → **Settings** → **Data Inputs** → **HTTP Event Collector**
2. **New Token** → Name: `fsxn-audit-log-shipper`
3. Source type: `fsxn:ontap:audit`, Index: `fsxn_audit`

```bash
aws secretsmanager create-secret \
  --name "splunk/fsxn-hec-token" \
  --secret-string '{"hec_token":"YOUR_HEC_TOKEN"}' \
  --region ap-northeast-1
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/splunk-serverless/template.yaml \
  --stack-name fsxn-splunk-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    SplunkHecTokenSecretArn=arn:aws:secretsmanager:...:secret:splunk/fsxn-hec-token-XXXXX \
    SplunkHecEndpoint=https://splunk.example.com:8088 \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Verify

```spl
index=fsxn_audit sourcetype=fsxn:ontap:audit | head 10
```

## Comparison: EC2-based vs Serverless

| Aspect | EC2-based (existing) | Serverless (this project) |
|--------|---------------------|--------------------------|
| Infra | EC2 × 2 (syslog-ng + UF) | Lambda + EventBridge |
| Monthly cost | ~$150+ | ~$5 (pay-per-use) |
| Scaling | Manual | Automatic |
| Patching | Required | Not needed |
| Availability | Manual HA | AWS managed |

## Network Considerations

- Splunk in VPC: Deploy Lambda in same VPC + NAT Gateway
- Splunk Cloud: Ensure HEC endpoint is publicly accessible
- Self-signed certs: Set `VerifySSL=false`
