# Getting Started

## Prerequisites

- AWS Account
- AWS CLI v2 configured
- Amazon FSx for NetApp ONTAP file system (audit logging enabled)
- Node.js 18+ (for development)
- Python 3.12+ (for Lambda functions)

## Setup Steps

### 1. Enable FSx for ONTAP Audit Logging

Enable audit logging on the FSx for ONTAP console or CLI, and configure output to an S3 bucket.

```bash
# Enable audit logging via ONTAP CLI
vserver audit create -vserver <svm-name> \
  -destination /vol/audit_logs \
  -format evtx \
  -rotate-size 100MB
```

### 2. Create S3 Access Point

```bash
aws s3control create-access-point \
  --account-id 123456789012 \
  --name fsxn-audit-ap \
  --bucket fsxn-audit-logs-bucket \
  --vpc-configuration VpcId=vpc-xxxxxxxx
```

### 3. Deploy Vendor Integration

Navigate to the vendor directory and deploy the CloudFormation template.

```bash
# Example: Datadog integration
cd integrations/datadog
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
  --capabilities CAPABILITY_IAM
```

### 4. Verify Operation

Perform file operations on FSx for ONTAP and verify logs are received on the vendor side.

## Next Steps

- [Architecture Details](architecture.md)
- [Vendor Comparison](vendor-comparison.md)
- [Datadog Setup Guide](../../integrations/datadog/docs/en/setup-guide.md)
