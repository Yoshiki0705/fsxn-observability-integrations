# FSx ONTAP S3 Access Points Specification

## Overview

Specification, constraints, and troubleshooting knowledge for FSx for ONTAP S3 Access Points used in this project.

---

## 1. Network Constraints (Most Critical)

### Root Cause

**FSx ONTAP S3 Access Points are NOT accessible via S3 Gateway VPC Endpoints.**

FSx ONTAP S3 APs route through the FSx data plane, not the standard S3 service endpoint (`com.amazonaws.<region>.s3`).

### Lambda Placement Patterns

| Lambda Placement | S3 AP Access | ONTAP REST API | Recommended Use |
|-----------------|-------------|---------------|----------------|
| Outside VPC | ✅ Works | ❌ Cannot | S3 AP read-only (primary pattern for this project) |
| In VPC + S3 Gateway EP | ❌ **TIMEOUT** | ✅ Works | ⚠️ Do NOT use |
| In VPC + NAT Gateway | ✅ Works | ✅ Works | Production recommended |
| In VPC + Interface EP only | ❌ **TIMEOUT** | ✅ Works | ⚠️ Do NOT use |

### Design Decision for This Project

```
[Recommended]
Lambda (no VPC) → S3 AP (via internet) → Read logs → Ship to Vendor API

[Production]
Lambda (VPC + NAT GW) → S3 AP (via NAT) → Read logs → Ship to Vendor API
```

---

## 2. ARN Format and IAM Policy

### Correct ARN Format
```
arn:aws:s3:{region}:{account-id}:accesspoint/{access-point-name}
```

### IAM Policy Resource
```yaml
# Object operations (GetObject, PutObject)
Resource: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap/object/*

# Bucket-level operations (ListBucket)
Resource: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap
```

### Common Mistakes
```yaml
# ❌ Wrong: standard S3 bucket ARN
Resource: arn:aws:s3:::my-bucket/*

# ❌ Wrong: missing /object/* suffix
Resource: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap/*

# ✅ Correct: with /object/* suffix
Resource: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap/object/*
```

---

## 3. S3 AP Resource Policy

In addition to IAM, the S3 Access Point itself requires a resource policy:

```bash
aws s3control put-access-point-policy \
  --account-id 123456789012 \
  --name fsxn-audit-ap \
  --policy '{"Version":"2012-10-17","Statement":[...]}'
```

---

## 4. boto3 Usage

```python
s3_client.get_object(
    Bucket="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
    Key="audit/svm-prod-01/2026/01/15/audit_log.json"
)
```

---

## 5. Unsupported S3 Features

| Feature | Status | Workaround |
|---------|--------|-----------|
| S3 Event Notifications / EventBridge | ❌ | Use standard S3 bucket EventBridge notifications |
| Object Lifecycle | ❌ | Custom cleanup Lambda |
| Object Versioning | ❌ | DynamoDB version tracking |
| Presigned URLs | ❌ | Copy to standard S3 + presign |
| SSE-KMS | ❌ (SSE-FSX only) | FSx volume-level KMS |
| PutObject > 5GB | ❌ | Multipart within 5GB |

---

## 6. Troubleshooting

### Symptom: Lambda timeout reading from S3 AP

**Cause**: Lambda in VPC with only S3 Gateway VPC Endpoint
**Fix**: Move Lambda outside VPC, or add NAT Gateway

### Symptom: AccessDenied

**Check 3 authorization layers**:
1. IAM policy (correct ARN with `/object/*`)
2. S3 AP resource policy (allows Lambda role)
3. FSx file system permissions (UNIX/NTFS ACLs)

### Symptom: ListObjectsV2 returns empty

**Causes**: Wrong prefix (FSx paths don't start with `/`), or S3 AP network origin mismatch

---

## References

- [AWS Docs — S3 AP API Support](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [AWS Docs — Managing S3 AP Access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [AWS Blog — S3 Access Points for FSx](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)
- [AWS Docs — Process files with Lambda](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
