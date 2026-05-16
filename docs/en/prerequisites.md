# Prerequisites and Resource Deployment Guide

## Overview

Before deploying any vendor integration from this project, the following prerequisite resources are required.

```
┌─────────────────────────────────────────────────────────────────┐
│              Prerequisite Resources (this guide)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FSx for ONTAP        S3 Bucket           S3 Access Point       │
│  (audit enabled)  →  (log storage)    →   (Lambda access)      │
│                                                                 │
│  EventBridge notifications enabled                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Vendor Integration Stack (integrations/)            │
├─────────────────────────────────────────────────────────────────┤
│  EventBridge Rule → Lambda → Vendor API                         │
└─────────────────────────────────────────────────────────────────┘
```

## Two Deployment Patterns

### Pattern A: Add to Existing FSx ONTAP Environment (Recommended)

Add the audit log delivery pipeline to an environment where FSx for ONTAP is already running.

**Prerequisites**:
- FSx for ONTAP file system exists
- SVM is created
- VPC, subnets, and security groups are configured

**Steps**:
1. [Step 1: Deploy Prerequisites Stack](#step-1-deploy-prerequisites-stack)
2. [Step 2: Enable FSx ONTAP Audit Logging](#step-2-enable-fsx-ontap-audit-logging)
3. [Step 3: Verify Log Delivery](#step-3-verify-log-delivery)
4. [Step 4: Deploy Vendor Integration](#step-4-deploy-vendor-integration)

### Pattern B: Build from Scratch (Testing/Demo)

Create all resources including FSx for ONTAP from scratch.

**Steps**:
1. [Step 0: Create FSx for ONTAP](#step-0-create-fsx-for-ontap-new-builds-only)
2. Continue with Pattern A steps

---

## Step 0: Create FSx for ONTAP (New Builds Only)

> ⚠️ FSx for ONTAP is billed hourly. Remember to delete after testing.

### Create via AWS CLI

```bash
aws fsx create-file-system \
  --file-system-type ONTAP \
  --storage-capacity 1024 \
  --storage-type SSD \
  --subnet-ids subnet-xxxxxxxx subnet-yyyyyyyy \
  --ontap-configuration '{
    "DeploymentType": "MULTI_AZ_1",
    "ThroughputCapacity": 128,
    "PreferredSubnetId": "subnet-xxxxxxxx",
    "FsxAdminPassword": "YourSecurePassword123!",
    "EndpointIpAddressRange": "198.19.0.0/24"
  }' \
  --tags Key=Project,Value=fsxn-observability \
  --region ap-northeast-1
```

### Create SVM

```bash
FS_ID=$(aws fsx describe-file-systems \
  --query "FileSystems[?Tags[?Key=='Project' && Value=='fsxn-observability']].FileSystemId" \
  --output text --region ap-northeast-1)

aws fsx create-storage-virtual-machine \
  --file-system-id $FS_ID \
  --name svm-audit-demo \
  --root-volume-security-style NTFS \
  --region ap-northeast-1
```

---

## Step 1: Deploy Prerequisites Stack

Creates S3 bucket, S3 Access Point, and enables EventBridge notifications.

```bash
aws cloudformation deploy \
  --template-file shared/templates/prerequisites.yaml \
  --stack-name fsxn-observability-prerequisites \
  --parameter-overrides \
    AuditLogBucketName=my-company-fsxn-audit-logs-ap-northeast-1 \
    AccessPointName=fsxn-audit-ap \
    VpcId=vpc-xxxxxxxx \
    RetentionDays=90 \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `AuditLogBucketName` | ✅ | - | S3 bucket name (globally unique) |
| `AccessPointName` | ❌ | `fsxn-audit-ap` | S3 Access Point name |
| `VpcId` | ❌ | - | Specify for VPC restriction |
| `RetentionDays` | ❌ | 90 | Days before Glacier transition |
| `EnableGlacierTransition` | ❌ | true | Enable/disable Glacier transition |
| `KmsKeyArn` | ❌ | - | Custom KMS key (defaults to aws/s3) |

### Verify Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-observability-prerequisites \
  --query "Stacks[0].Outputs" \
  --output table --region ap-northeast-1
```

Key outputs:
- `AccessPointArn` — Use as `S3AccessPointArn` parameter in vendor stacks
- `AuditLogBucketName` — Configure as FSx ONTAP audit log destination

---

## Step 2: Enable FSx ONTAP Audit Logging

### Method A: Use the Setup Script (Recommended)

```bash
# Dry run (preview commands only)
bash shared/scripts/ontap-audit-setup.sh \
  --endpoint 10.0.1.100 \
  --svm svm-prod-01 \
  --format evtx \
  --dry-run

# Execute
bash shared/scripts/ontap-audit-setup.sh \
  --endpoint 10.0.1.100 \
  --svm svm-prod-01 \
  --format evtx
```

### Method B: ONTAP System Manager (GUI)

1. FSx Console → File System → Open management endpoint URL in browser
2. **Storage** → **SVMs** → Select target SVM
3. **Settings** → **Audit** → **Enable**
4. Configure: Destination `/vol/audit_logs`, Format EVTX, Rotation 100MB

### Method C: Manual SSH

```bash
ssh admin@<management-endpoint-ip>

vserver audit create -vserver svm-prod-01 \
  -destination /vol/audit_logs \
  -format evtx \
  -rotate-size 100MB

vserver audit enable -vserver svm-prod-01
vserver audit show -vserver svm-prod-01
```

### Audit Log S3 Delivery Options

#### Option 1: FSx Automatic Backups + S3 Export
Use FSx automatic backups and export to S3. Low real-time capability but simple setup.

#### Option 2: DataSync Periodic Sync

```bash
aws datasync create-task \
  --source-location-arn arn:aws:datasync:ap-northeast-1:123456789012:location/loc-xxxxx \
  --destination-location-arn arn:aws:datasync:ap-northeast-1:123456789012:location/loc-yyyyy \
  --schedule "ScheduleExpression=rate(5 minutes)" \
  --name fsxn-audit-sync
```

#### Option 3: FSx ONTAP S3 Access Point (Recommended, Latest)

FSx ONTAP S3 Access Points (released 2025) allow direct S3 API access to volume data. Attach an S3 Access Point to the audit log volume for direct Lambda read access.

> 📝 FSx ONTAP S3 Access Points differ from regular S3 Access Points. They attach directly to FSx volumes, providing S3 API access to NFS/SMB data.

---

## Step 3: Verify Log Delivery

```bash
# Check objects in bucket
aws s3 ls s3://my-company-fsxn-audit-logs-ap-northeast-1/audit/ --recursive

# Upload test file
aws s3 cp integrations/datadog/tests/test_data/sample_audit_logs.json \
  s3://my-company-fsxn-audit-logs-ap-northeast-1/audit/svm-prod-01/2026/01/15/test_audit.json
```

---

## Step 4: Deploy Vendor Integration

```bash
# Get prerequisite stack outputs
AP_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-observability-prerequisites \
  --query "Stacks[0].Outputs[?OutputKey=='AccessPointArn'].OutputValue" \
  --output text --region ap-northeast-1)

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name fsxn-observability-prerequisites \
  --query "Stacks[0].Outputs[?OutputKey=='AuditLogBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

# Deploy Datadog integration
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
    DatadogSite=datadoghq.com \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

---

## Troubleshooting

### Audit logs not arriving in S3

1. **Check FSx ONTAP side**:
   ```
   ssh admin@<endpoint>
   vserver audit show -vserver <svm-name> -fields state
   ```

2. **Check volume**:
   ```
   volume show -vserver <svm-name> -volume audit_logs
   ```

3. **Check S3 delivery configuration** (DataSync task status or FSx S3 AP)

### EventBridge events not firing

1. Verify EventBridge notifications are enabled on the bucket:
   ```bash
   aws s3api get-bucket-notification-configuration --bucket <bucket-name>
   ```
   Confirm `EventBridgeConfiguration` is present.

2. Redeploy the prerequisites stack (includes notification config).

### S3 Access Point read errors

1. Verify Lambda IAM role has `s3:GetObject` permission
2. Confirm resource ARN uses `<access-point-arn>/object/*` format
3. If VPC-restricted, ensure Lambda is in the same VPC

---

## References

- [FSx ONTAP File Access Auditing](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)
- [S3 Access Points for FSx](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)
- [Process Files Serverlessly with Lambda](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [Using EventBridge with S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventBridge.html)
- [NetApp Workload Factory - Journal Table](https://docs.netapp.com/us-en/workload-fsx-ontap/setup-journal-table.html)
