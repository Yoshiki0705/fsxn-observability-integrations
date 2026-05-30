# Datadog Setup Guide

## Overview

Setup guide for the serverless integration that ships Amazon FSx for NetApp ONTAP audit logs to Datadog Logs.

## Prerequisites

- AWS Account (FSx for ONTAP running)
- Datadog Account (Logs feature enabled)
- AWS CLI v2 configured
- FSx for ONTAP audit logs outputting to an S3 bucket

## Step 1: Prepare Datadog API Key

### 1.1 Get API Key from Datadog

1. Log in to Datadog console
2. Navigate to **Organization Settings** → **API Keys**
3. Click **New Key** to create a new API Key
4. Key name: `fsxn-audit-log-shipper`
5. Copy the generated API Key

### 1.2 Store in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name "datadog/fsxn-api-key" \
  --description "Datadog API Key for FSxN audit log integration" \
  --secret-string '{"api_key":"YOUR_DATADOG_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: Configure S3 Access Point

Create an S3 Access Point for the FSx for ONTAP audit log bucket (if not already created).

```bash
aws s3control create-access-point \
  --account-id YOUR_ACCOUNT_ID \
  --name fsxn-audit-ap \
  --bucket YOUR_AUDIT_LOG_BUCKET \
  --region ap-northeast-1
```

## Step 3: Deploy CloudFormation

```bash
cd integrations/datadog

aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog/fsxn-api-key-XXXXXX \
    DatadogSite=datadoghq.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### Parameter Reference

| Parameter | Description |
|-----------|-------------|
| `FsxS3AccessPointArn` | FSx for ONTAP S3 Access Point ARN (attached to audit volume) |
| `DatadogApiKeySecretArn` | Secrets Manager ARN for the API Key |
| `DatadogSite` | Datadog site (see below) |

### Datadog Sites

| Site | Domain | Use Case | Logs Intake Endpoint |
|------|--------|----------|---------------------|
| US1 | `datadoghq.com` | US East (default) | `http-intake.logs.datadoghq.com` |
| US3 | `us3.datadoghq.com` | US (Azure integration) | `http-intake.logs.us3.datadoghq.com` |
| US5 | `us5.datadoghq.com` | US West | `http-intake.logs.us5.datadoghq.com` |
| EU1 | `datadoghq.eu` | EU (Frankfurt) | `http-intake.logs.datadoghq.eu` |
| AP1 | `ap1.datadoghq.com` | Asia Pacific (Tokyo) | `http-intake.logs.ap1.datadoghq.com` |
| AP2 | `ap2.datadoghq.com` | Asia Pacific (Sydney) | `http-intake.logs.ap2.datadoghq.com` |
| US1-FED | `ddog-gov.com` | US Government (FedRAMP) | `http-intake.logs.ddog-gov.com` |

> **Region selection guide**:
> - APAC (Japan, Australia, etc.): `ap1.datadoghq.com` or `ap2.datadoghq.com`
> - EMEA (Europe, Middle East, Africa): `datadoghq.eu`
> - AMERICAS (North/South America): `datadoghq.com`, `us3.datadoghq.com`, `us5.datadoghq.com`
> - US Government: `ddog-gov.com`

## Step 4: Datadog Configuration

### 4.1 Create Log Pipeline

1. Datadog console → **Logs** → **Configuration** → **Pipelines**
2. Click **New Pipeline**
3. Configuration:
   - **Filter**: `source:fsxn`
   - **Name**: `FSx for ONTAP Audit Logs`

### 4.2 Add Processors to Pipeline

#### Grok Parser
```
# Parse rule for FSx for ONTAP audit logs
fsxn_audit %{data:attributes}
```

#### Status Remapper
- **Status attribute**: `attributes.result`

#### Date Remapper
- **Date attribute**: `attributes.timestamp`

### 4.3 Create Facets

Register the following fields as Facets for easier searching:

| Facet | Path | Type |
|-------|------|------|
| SVM | `@attributes.svm` | String |
| User | `@attributes.user` | String |
| Operation | `@attributes.operation` | String |
| Client IP | `@attributes.client_ip` | String |
| Result | `@attributes.result` | String |
| File Path | `@attributes.path` | String |

### 4.4 Create Dashboard (Recommended)

Create a Datadog dashboard for FSx for ONTAP audit logs:

- **Log Volume Trend**: Time series of `source:fsxn` log count
- **Operations Breakdown**: Top list by `@attributes.operation`
- **User Activity**: Top list by `@attributes.user`
- **Error Rate**: Percentage of `@attributes.result:failure`

## Step 5: Verification

### 5.1 Generate Test Events

Perform file operations on FSx for ONTAP:

```bash
# File operations on FSx for ONTAP mount point
echo "test" > /mnt/fsxn/test-audit.txt
cat /mnt/fsxn/test-audit.txt
rm /mnt/fsxn/test-audit.txt
```

### 5.2 Verify in Datadog

1. Datadog console → **Logs** → **Search**
2. Search query: `source:fsxn`
3. Verify logs appear within a few minutes

### 5.3 Check Lambda in CloudWatch

```bash
aws logs tail /aws/lambda/fsxn-datadog-integration-shipper --follow
```

## Troubleshooting

### Logs Not Appearing in Datadog

1. **Check Lambda errors**:
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/fsxn-datadog-integration-shipper \
     --filter-pattern "ERROR"
   ```

2. **Check DLQ messages**:
   ```bash
   aws sqs get-queue-attributes \
     --queue-url https://sqs.ap-northeast-1.amazonaws.com/123456789012/fsxn-datadog-integration-dlq \
     --attribute-names ApproximateNumberOfMessages
   ```

3. **Verify API Key**: Confirm the Secrets Manager value is correct

4. **Check timestamps**: Datadog uses the log's `date` field for indexing. If the log timestamp is too old (outside the retention window), it won't appear in search results. Use current timestamps when testing.

5. **Verify Datadog site**: Ensure the Lambda environment variable `DATADOG_SITE` points to the correct site. For Japan region, use `ap1.datadoghq.com`.

### Using VPC-Restricted S3 Access Points

When the S3 Access Point is restricted to a VPC, Lambda must run in the same VPC. Add the following parameters during CloudFormation deployment:

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog/fsxn-api-key-XXXXXX \
    DatadogSite=ap1.datadoghq.com \
    VpcEnabled=true \
    VpcSubnetIds=subnet-xxx,subnet-yyy \
    VpcSecurityGroupIds=sg-xxx \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

> **Note**: Lambda in a VPC requires a NAT Gateway or VPC endpoint to access the Datadog API. A VPC endpoint for Secrets Manager (`com.amazonaws.ap-northeast-1.secretsmanager`) is also required.

### Known Issue with gzip Compression

Currently, gzip-compressed payloads may not be correctly indexed on the Datadog AP1 site (`ap1.datadoghq.com`). Lambda is configured to send uncompressed payloads. If payload size becomes an issue in high-volume environments, contact Datadog support regarding gzip support status.

### Rate Limiting Errors

When Datadog API rate limits are hit, Lambda automatically retries with exponential backoff. If this occurs frequently, limit Lambda concurrency:

```bash
aws lambda put-function-concurrency \
  --function-name fsxn-datadog-integration-shipper \
  --reserved-concurrent-executions 5
```

### Deploying Lambda Code

The CloudFormation template deploys with placeholder code. To deploy the actual handler.py:

```bash
# Package Lambda code
cd integrations/datadog/lambda
zip function.zip handler.py

# Update Lambda function code
aws lambda update-function-code \
  --function-name fsxn-datadog-integration-shipper \
  --zip-file fileb://function.zip \
  --region ap-northeast-1
```

> **Note**: For CI/CD pipelines, deploying via S3 bucket is recommended.
