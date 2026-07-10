# Multi-Account Deployment with AWS Organizations

🌐 [日本語](../ja/multi-account-deployment.md) | **English** (this page)

## Overview

Deploy FSx for ONTAP observability pipelines across multiple AWS accounts using CloudFormation StackSets. This pattern enables centralized management of audit log pipelines while keeping data processing local to each account.

## Architecture

```
Management Account
  |
  CloudFormation StackSet (service-managed permissions)
  |
  +---> Account A (ap-northeast-1)
  |       Lambda + EventBridge + DLQ + Secrets Manager
  |
  +---> Account B (ap-northeast-1)
  |       Lambda + EventBridge + DLQ + Secrets Manager
  |
  +---> Account C (us-east-1)
          Lambda + EventBridge + DLQ + Secrets Manager

Centralized: StackSet management, cross-account dashboard
Per-account: FSx for ONTAP, S3 AP, vendor credentials, audit data
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Permission model | SERVICE_MANAGED | No manual IAM roles in target accounts |
| Data locality | Per-account processing | Audit logs never leave source account |
| Credential isolation | Per-account Secrets Manager | No cross-account credential sharing |
| Auto-deployment | Enabled by default | New accounts get pipeline automatically |
| Failure tolerance | 10% | Limits blast radius of bad template updates |

## Prerequisites

### 1. AWS Organizations Setup

```bash
# Verify Organizations is enabled
aws organizations describe-organization \
  --query 'Organization.{Id:Id, MasterAccountId:MasterAccountId}'

# Enable StackSets trusted access
aws organizations enable-aws-service-access \
  --service-principal member.org.stacksets.cloudformation.amazonaws.com
```

### 2. Per-Account Preparation

Each target account needs:

1. **FSx for ONTAP with audit logging enabled**
2. **S3 Access Point ARN stored in SSM Parameter Store**:
   ```bash
   aws ssm put-parameter \
     --name "/fsxn/s3-access-point-arn" \
     --value "arn:aws:s3:<region>:<account-id>:accesspoint/fsxn-audit-ap" \
     --type String
   ```
3. **Vendor credentials in Secrets Manager**:
   ```bash
   aws secretsmanager create-secret \
     --name "<vendor>/fsxn-credentials" \
     --secret-string '{"api_key":"<key>"}'
   ```

### 3. Template Upload

Upload the vendor template to an S3 bucket accessible by all accounts:

```bash
aws s3 cp integrations/<vendor>/template.yaml \
  s3://<stackset-templates-bucket>/<vendor>/template.yaml
```

## Deployment

```bash
aws cloudformation deploy \
  --template-file shared/templates/multi-account-stackset.yaml \
  --stack-name fsxn-<vendor>-stackset-admin \
  --parameter-overrides \
    OrganizationalUnitIds=ou-xxxx-yyyyyyyy \
    VendorName=<vendor> \
    VendorTemplateUrl=https://s3.<region>.amazonaws.com/<bucket>/<vendor>/template.yaml \
    VendorCredentialSecretName=<vendor>/fsxn-credentials \
    Regions=ap-northeast-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

## Monitoring

```bash
# Check per-account instance status
aws cloudformation list-stack-instances \
  --stack-set-name fsxn-<vendor>-observability-pipeline \
  --call-as SELF \
  --query 'Summaries[].{Account:Account, Region:Region, Status:StackInstanceStatus.DetailedStatus}'
```

## Cross-Account Observability

For centralized monitoring across all accounts, enable CloudWatch cross-account observability or aggregate alarms to a central SNS topic with Organization-scoped publish permissions.

## Operational Procedures

### Adding a New Account
1. Account joins the target OU
2. StackSet auto-deploys (if AutoDeployment=true)
3. Create SSM parameter and Secrets Manager secret in new account
4. Verify StackSet instance status

### Removing an Account
1. Account leaves the OU
2. StackSet auto-removes stack
3. Manual cleanup of Secrets Manager if needed

### Troubleshooting Failed Instances
```bash
aws cloudformation describe-stack-instance \
  --stack-set-name fsxn-<vendor>-observability-pipeline \
  --stack-instance-account <account-id> \
  --stack-instance-region <region> \
  --call-as SELF \
  --query 'StackInstance.StatusReason'
```

## Security Considerations

- Each account has its own Secrets Manager secret (no cross-account credential sharing)
- Audit logs never leave the source account
- FailureTolerancePercentage limits blast radius
- S3 bucket policy restricts template access to Organization only

## Related Documents

- [Pipeline SLO](pipeline-slo.md)
- [Compliance Evidence Pack](compliance-evidence-pack.md)
- [Cross-Region Replication](cross-region-replication.md)
