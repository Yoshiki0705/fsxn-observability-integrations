# FSx ONTAP S3 Access Points Specification

## Overview

Specification, constraints, and troubleshooting knowledge for FSx for ONTAP S3 Access Points used in this project.

---

## 1. Network Constraints (Most Critical)

### Root Cause

**Internet-origin FSx ONTAP S3 Access Points timed out when accessed from VPC Lambda with only a Gateway Endpoint (observed in our environment).**

AWS [documents](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html) that VPC-origin access points work with Gateway Endpoints for traffic originating within the bound VPC. For Internet-origin APs, NAT Gateway or VPC-external Lambda is required.

### Lambda Placement Patterns

| Lambda Placement | S3 AP Access | ONTAP REST API | Recommended Use |
|-----------------|-------------|---------------|----------------|
| Outside VPC | ✅ Works | ❌ Cannot | S3 AP read-only (primary pattern for this project) |
| In VPC + S3 Gateway EP (Internet-origin AP) | ⚠️ **TIMEOUT** | ✅ Works | Use NAT or VPC-origin AP |
| In VPC + NAT Gateway | ✅ Works | ✅ Works | Production recommended |
| In VPC + VPC-origin AP + Gateway EP | ✅ Expected per AWS docs | ✅ Works | Requires VPC-origin AP |

### Design Decision for This Project

```
[Recommended]
Lambda (no VPC) → S3 AP (via internet) → Read logs → Ship to Vendor API

[Production]
Lambda (VPC + NAT GW) → S3 AP (via NAT) → Read logs → Ship to Vendor API
```

**Important**: The S3 Access Point in `shared/templates/prerequisites.yaml` is created with `NetworkOrigin: Internet`. If VPC restriction is required, a NAT Gateway is mandatory.

---

## 2. ARN Format and IAM Policy

### Correct ARN Format
```
arn:aws:s3:{region}:{account-id}:accesspoint/{access-point-name}
```

### IAM Policy Resource
```yaml
# Object operations (GetObject, PutObject)
Resource: !Sub 'arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${AccessPointName}/object/*'

# Bucket-level operations (ListBucket)
Resource: !Sub 'arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${AccessPointName}'
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
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "AllowLambdaRead",
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::123456789012:role/fsxn-datadog-lambda-role"},
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap/object/*"
      ]
    }]
  }'
```

---

## 4. boto3 Usage

```python
import boto3

s3_client = boto3.client("s3")

# Use S3 AP ARN as the Bucket parameter
response = s3_client.get_object(
    Bucket="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
    Key="audit/svm-prod-01/2026/01/15/audit_log.json"
)

# ListObjectsV2 works the same way
response = s3_client.list_objects_v2(
    Bucket="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
    Prefix="audit/svm-prod-01/"
)
```

---

## 5. Unsupported S3 APIs / Features

| Feature | Status | Impact | Workaround |
|---------|--------|--------|-----------|
| GetBucketNotificationConfiguration | ❌ | Cannot use event-driven triggers | Use standard S3 bucket EventBridge notifications |
| S3 Event Notifications | ❌ | Cannot directly trigger Lambda | Use EventBridge Rule |
| Object Lifecycle | ❌ | No automatic deletion/transition | Custom Lambda for periodic cleanup |
| Object Versioning | ❌ | No version management | DynamoDB version tracking |
| Presigned URLs | ❌ | No time-limited sharing | Copy to standard S3 + presign |
| SSE-KMS | ❌ | No custom KMS keys | FSx volume-level KMS encryption |
| PutObject > 5GB | ❌ | Cannot write large files | Multipart Upload (within 5GB) |

---

## 6. Troubleshooting

### Symptom: Lambda timeout reading from S3 AP

**Cause**: Lambda is in a VPC with only an S3 Gateway VPC Endpoint configured

**Fix**:
1. Move Lambda outside VPC (recommended)
2. Or add a NAT Gateway

**Verification commands**:
```bash
# Check Lambda VPC configuration
aws lambda get-function-configuration \
  --function-name fsxn-datadog-integration-shipper \
  --query 'VpcConfig'

# Check VPC Endpoints
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-xxx" \
  --query 'VpcEndpoints[*].{Service:ServiceName,Type:VpcEndpointType}'
```

### Symptom: AccessDenied

**Check 3 authorization layers**:
1. **IAM policy**: Lambda role has `s3:GetObject` + correct ARN format
2. **S3 AP resource policy**: Allows the Lambda role
3. **FSx file system permissions**: UNIX/NTFS ACLs for the user associated with the S3 AP

```bash
# Check IAM policy
aws iam get-role-policy --role-name <lambda-role> --policy-name S3AccessPointRead

# Check S3 AP policy
aws s3control get-access-point-policy --account-id <account> --name <ap-name>
```

### Symptom: ListObjectsV2 returns empty results

**Possible causes**:
- Incorrect prefix (FSx ONTAP path structure does not start with `/`)
- S3 AP network origin is `VPC` and Lambda is in a different VPC

---

## 7. Test Design Considerations

### Unit Tests
- Verify that S3 AP ARN is passed as the `Bucket` parameter in tests
- Set `S3_ACCESS_POINT_ARN` environment variable in `conftest.py`

### Integration Tests
- Prioritize testing with Lambda outside VPC (avoids network issues)
- Run VPC-based tests only after confirming NAT Gateway is available

### CloudFormation Tests
- Validate ARN patterns with `cfn-lint`
- Verify `/object/*` suffix on IAM resources

---

## References

- [AWS Docs — FSx ONTAP S3 AP API Support](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)
- [AWS Docs — Managing S3 AP Access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)
- [AWS Blog — S3 Access Points for FSx](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)
- [AWS Docs — Process files with Lambda](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-process-files-with-lambda.html)
- [AWS Blog — AI-powered analytics with S3 AP + AD](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/)
