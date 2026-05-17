# Architecture

## Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  FSx for ONTAP  │────▶│  FSx ONTAP       │────▶│  EventBridge    │
│  (Audit Logs)   │     │  S3 Access Point │     │  Scheduler      │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Observability  │◀────│     Lambda       │◀────│  Periodic       │
│  Vendor API     │     │  (Transform/Ship)│     │  + checkpoint   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Component Details

### 1. FSx for NetApp ONTAP Audit Logs

Enable audit logging on FSx for ONTAP to output logs to an audit volume inside the SVM.

- **Log Format**: EVTX (Windows Event Log, default) or XML
- **Destination**: Audit volume inside the SVM (`vserver audit create -destination /audit_log`)
- **Log Content**: File access (SMB/NFS), authentication events
- **Access Method**: Read via FSx for ONTAP S3 Access Point using S3 APIs

> **Important**: Audit logs are stored on the FSx volume. They are NOT written to an S3 bucket. Lambda reads the log files through an FSx for ONTAP S3 Access Point using S3 APIs.

### 2. FSx for ONTAP S3 Access Point

An S3 Access Point attached to an FSx for ONTAP volume.

- **Purpose**: Serverless access boundary for Lambda to read audit logs without NFS/SMB mounts
- **Characteristics**: Data remains on the FSx file system, accessible via S3 API
- **Limitation**: S3 Event Notifications / EventBridge notifications are NOT supported
- **VPC Constraint**: NOT accessible via S3 Gateway VPC Endpoints (NAT Gateway required)

### 3. Trigger Mechanism

Because FSx for ONTAP S3 Access Points do not support S3 event notifications, we use EventBridge Scheduler for periodic invocation.

**EventBridge Scheduler + Checkpointing**
- EventBridge Scheduler invokes Lambda periodically (e.g., every 5 minutes)
- Lambda tracks processed files via checkpointing (DynamoDB)
- Only newly rotated log files are processed

### 4. Lambda Function

Retrieves and parses audit logs, then ships to vendor APIs.

- **Runtime**: Python 3.12
- **Processing Flow**:
  1. List log files via FSx for ONTAP S3 Access Point
  2. Compare with checkpoint to identify unprocessed files
  3. Parse EVTX/XML
  4. Transform to vendor-specific format
  5. Batch send to API endpoint
  6. Retry on failure (exponential backoff)
  7. Update checkpoint

### 5. Alternative Pattern: Kinesis Data Firehose

For high-volume logs, deliver to vendors via Firehose.

```
FSx S3 AP → Lambda (Transform) → Kinesis Data Firehose → Vendor API
```

- **Benefits**: Automatic buffering, retry, scaling
- **Supported Vendors**: Splunk (HEC), Datadog, New Relic, any HTTP endpoint

## Security Design

### IAM Least Privilege

```yaml
# Lambda execution role
- s3:GetObject (FSx ONTAP S3 Access Point ARN only)
- s3:ListBucket (FSx ONTAP S3 Access Point ARN only)
- secretsmanager:GetSecretValue (API Key Secret only)
- dynamodb:GetItem, dynamodb:PutItem (checkpoint table only)
- logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
```

### Secret Management

- API keys stored in AWS Secrets Manager
- Only ARN set in Lambda environment variables
- KMS customer-managed key encryption recommended

### Network

- Access FSx for ONTAP S3 Access Point via NAT Gateway (when Lambda is in VPC)
- **Note**: S3 Gateway VPC Endpoints do NOT work for FSx ONTAP S3 APs
- Lambda placed outside VPC can access FSx ONTAP S3 AP without issues (recommended for read-only)
- Security groups allow minimal outbound only

## Monitoring & Alerting

- **CloudWatch Metrics**: Lambda error rate, duration, throttling
- **CloudWatch Alarms**: SNS notification on delivery failure threshold
- **Dead Letter Queue**: Failed events sent to SQS DLQ
- **X-Ray**: Distributed tracing for bottleneck identification
