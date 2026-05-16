# Architecture

## Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  FSx for ONTAP  │────▶│  S3 Access Point │────▶│   EventBridge   │
│  (Audit Logs)   │     │  (Log Output)    │     │  / S3 Event     │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Observability  │◀────│     Lambda       │◀────│  EventBridge    │
│  Vendor API     │     │  (Transform/Ship)│     │  Rule           │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Component Details

### 1. FSx for NetApp ONTAP Audit Logs

Enable audit logging on FSx for ONTAP to output logs to an S3 bucket.

- **Log Format**: EVTX (Windows Event Log) or JSON
- **Destination**: S3 bucket (access controlled via S3 Access Point)
- **Log Content**: File access, administrative operations, authentication events

### 2. S3 Access Point

S3 Access Points provide fine-grained access control to audit logs.

- **Purpose**: Granular access control, VPC restrictions
- **Benefit**: Manage access without modifying bucket policies
- **VPC Restriction**: Optionally restrict access to VPC endpoint only

### 3. Event Notification

Trigger Lambda on object creation in the S3 Access Point.

**Pattern A: EventBridge**
- S3 event notifications sent to EventBridge
- EventBridge rules for filtering
- Lambda as target

**Pattern B: S3 Event Notification**
- Direct S3 bucket event notification to Lambda
- Simpler but limited filtering capabilities

### 4. Lambda Function

Retrieves and parses audit logs, then ships to vendor APIs.

- **Runtime**: Python 3.12
- **Processing Flow**:
  1. Retrieve log file from S3 Access Point
  2. Parse EVTX/JSON
  3. Transform to vendor-specific format
  4. Batch send to API endpoint
  5. Retry on failure (exponential backoff)

### 5. Alternative Pattern: Kinesis Data Firehose

For high-volume logs, deliver directly to vendors via Firehose.

```
S3 AP → Lambda (Transform) → Kinesis Data Firehose → Vendor API
```

- **Benefits**: Automatic buffering, retry, scaling
- **Supported Vendors**: Splunk (HEC), Datadog, New Relic, any HTTP endpoint

## Security Design

### IAM Least Privilege

```yaml
# Lambda execution role
- s3:GetObject (Access Point ARN only)
- secretsmanager:GetSecretValue (API Key Secret only)
- logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
- kms:Decrypt (when using encryption keys)
```

### Secret Management

- API keys stored in AWS Secrets Manager
- Only ARN set in Lambda environment variables
- KMS customer-managed key encryption recommended

### Network

- Access S3 Access Point via VPC endpoint
- Lambda deployed in VPC (NAT Gateway for external API calls)
- Security groups allow minimal outbound only

## Monitoring & Alerting

- **CloudWatch Metrics**: Lambda error rate, duration, throttling
- **CloudWatch Alarms**: SNS notification on delivery failure threshold
- **Dead Letter Queue**: Failed events sent to SQS DLQ
- **X-Ray**: Distributed tracing for bottleneck identification
