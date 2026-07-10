# Compliance Evidence Pack Template

🌐 [日本語](../ja/compliance-evidence-pack.md) | **English** (this page)

## Overview

This template helps organizations assemble compliance evidence for FSx for ONTAP observability pipelines. It maps pipeline controls to regulatory frameworks and provides a checklist for audit preparation.

> **Governance caveat**: This template provides a structure for evidence collection. It does not constitute a compliance assessment or certification. Engage your compliance team or auditor to validate that evidence meets your specific regulatory requirements.

## Applicable Frameworks

| Framework | Scope | Key Controls for This Pipeline |
|-----------|-------|-------------------------------|
| **ISMAP** | Japan Gov Cloud | Audit logging, access control, encryption, monitoring |
| **FISC** | Japan Financial | Data retention (7yr), access trail, change management |
| **SOC 2** | Service Organizations | Logical access, monitoring, incident response |
| **ISO 27001** | Information Security | A.12.4 Logging, A.12.6 Vulnerability mgmt |
| **PCI DSS** | Payment Card | Req 10: Track access, Req 10.7: Retention |
| **APPI** | Japan Personal Info | Purpose limitation, cross-border transfer, retention |

## Evidence Categories

### 1. Data Flow Documentation

**Required evidence**:
- [ ] Architecture diagram showing data flow from FSx for ONTAP to vendor
- [ ] Network path documentation (VPC, endpoints, NAT, internet)
- [ ] Data classification of fields in transit (see [Data Classification Guide](data-classification.md))
- [ ] Encryption in transit verification (TLS 1.2+ for all vendor APIs)
- [ ] Encryption at rest verification (KMS for DLQ, SSE for DynamoDB)

**Where to find it**:
- Architecture: `docs/en/architecture.md`
- Data classification: `docs/en/data-classification.md`
- Encryption: CloudFormation template `Properties.KmsMasterKeyId`

### 2. Access Control

**Required evidence**:
- [ ] IAM policy documents (Lambda execution role)
- [ ] S3 Access Point resource policy
- [ ] Secrets Manager access policy
- [ ] Principle of least privilege verification
- [ ] No wildcard (`*`) actions in IAM policies
- [ ] Vendor platform RBAC configuration

**Where to find it**:
```bash
# Export IAM policies from deployed stack
aws cloudformation describe-stack-resources \
  --stack-name fsxn-<vendor>-integration \
  --query 'StackResources[?ResourceType==`AWS::IAM::Role`].PhysicalResourceId'

# Get role policy
aws iam get-role-policy \
  --role-name <role-name> \
  --policy-name <policy-name>
```

### 3. Audit Trail

**Required evidence**:
- [ ] CloudTrail enabled for Lambda invocations
- [ ] CloudWatch Logs retention configured (30+ days)
- [ ] DLQ message retention (14 days)
- [ ] Checkpoint history (SSM Parameter Store version history)
- [ ] Object ledger (DynamoDB, if Level 3)
- [ ] Vendor-side audit log of API access

**Where to find it**:
```bash
# CloudWatch Log Group retention
aws logs describe-log-groups \
  --log-group-name-prefix /aws/lambda/fsxn- \
  --query 'logGroups[].{Name:logGroupName, Retention:retentionInDays}'

# SSM Parameter history
aws ssm get-parameter-history \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --query 'Parameters[-5:].[Version, LastModifiedDate, Value]'
```

### 4. Monitoring and Alerting

**Required evidence**:
- [ ] CloudWatch Alarms configured (Lambda errors, DLQ depth)
- [ ] Alarm notification targets (SNS topic, email)
- [ ] Pipeline SLO definitions (see [Pipeline SLO](pipeline-slo.md))
- [ ] Incident response runbooks (see [Runbooks](runbooks/))
- [ ] Alarm history (last 90 days)

**Where to find it**:
```bash
# List alarms for the pipeline
aws cloudwatch describe-alarms \
  --alarm-name-prefix fsxn- \
  --query 'MetricAlarms[].{Name:AlarmName, State:StateValue, Actions:AlarmActions}'
```

### 5. Data Retention

**Required evidence**:
- [ ] Retention policy documented (see [Retention Policy Matrix](retention-policy-matrix.md))
- [ ] Vendor retention configuration screenshot/export
- [ ] S3 Lifecycle rules (if archiving to S3)
- [ ] DynamoDB TTL configuration (if using object ledger)
- [ ] Evidence that retention meets regulatory minimum

### 6. Change Management

**Required evidence**:
- [ ] Infrastructure as Code (CloudFormation templates in Git)
- [ ] Git commit history for all changes
- [ ] CI/CD pipeline configuration (`.github/workflows/ci.yaml`)
- [ ] PR review process (branch protection rules)
- [ ] Deployment history (CloudFormation stack events)

### 7. Vulnerability Management

**Required evidence**:
- [ ] Lambda runtime version (Python 3.12 — supported)
- [ ] Dependency scan results (Trivy in CI)
- [ ] cfn-guard security rule results
- [ ] No known CVEs in Lambda layers
- [ ] Secrets rotation schedule

### 8. Data Residency

**Required evidence**:
- [ ] Vendor deployment region documented
- [ ] Cross-border data transfer assessment (if applicable)
- [ ] Data residency matrix (see [Data Residency](data-residency.md))
- [ ] No data stored outside approved regions

## Framework-Specific Checklists

### ISMAP Checklist

| Control | Evidence | Status |
|---------|----------|--------|
| 8.1.1 Audit logging | CloudWatch Logs + vendor platform | [ ] |
| 8.1.2 Log protection | KMS encryption on DLQ, CloudWatch | [ ] |
| 8.1.3 Log retention | 1 year minimum (paid vendor tier) | [ ] |
| 9.1.1 Access control | IAM least privilege + S3 AP policy | [ ] |
| 9.4.1 Encryption in transit | TLS 1.2+ to vendor API | [ ] |
| 9.4.2 Encryption at rest | KMS (DLQ), SSE (DynamoDB) | [ ] |
| 12.1.1 Monitoring | CloudWatch Alarms + SLO | [ ] |
| 12.1.2 Incident response | Runbooks + escalation path | [ ] |

### FISC Checklist

| Control | Evidence | Status |
|---------|----------|--------|
| Access trail | Audit logs shipped to vendor | [ ] |
| 7-year retention | S3 Glacier archive + vendor retention | [ ] |
| Change management | Git + CloudFormation + CI/CD | [ ] |
| Encryption | TLS in transit, KMS at rest | [ ] |
| Monitoring | Alarms + SLO + runbooks | [ ] |
| Data residency | JP region vendor or self-hosted | [ ] |

### SOC 2 (Trust Services Criteria)

| Criteria | Control | Evidence | Status |
|----------|---------|----------|--------|
| CC6.1 | Logical access | IAM policies, S3 AP policy | [ ] |
| CC6.2 | Access provisioning | Secrets Manager, no hardcoded creds | [ ] |
| CC7.2 | Monitoring | CloudWatch Alarms, SLO | [ ] |
| CC7.3 | Incident response | Runbooks, DLQ replay | [ ] |
| CC8.1 | Change management | Git, CI/CD, CloudFormation | [ ] |
| A1.2 | Recovery | DLQ, checkpoint, retry | [ ] |

## Evidence Collection Script

```bash
#!/bin/bash
# Collect compliance evidence for a specific vendor integration
VENDOR="${1:-datadog}"
STACK_NAME="fsxn-${VENDOR}-integration"
OUTPUT_DIR="evidence/${VENDOR}/$(date +%Y-%m-%d)"
mkdir -p "$OUTPUT_DIR"

echo "Collecting evidence for: $STACK_NAME"

# 1. Stack resources and policies
aws cloudformation describe-stack-resources \
  --stack-name "$STACK_NAME" > "$OUTPUT_DIR/stack-resources.json"

# 2. IAM policies
for role in $(aws cloudformation describe-stack-resources \
  --stack-name "$STACK_NAME" \
  --query 'StackResources[?ResourceType==`AWS::IAM::Role`].PhysicalResourceId' \
  --output text); do
  aws iam get-role --role-name "$role" > "$OUTPUT_DIR/iam-role-${role}.json"
done

# 3. CloudWatch Alarms
aws cloudwatch describe-alarms \
  --alarm-name-prefix "fsxn-${VENDOR}" > "$OUTPUT_DIR/alarms.json"

# 4. Log group retention
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/fsxn-${VENDOR}" > "$OUTPUT_DIR/log-groups.json"

# 5. Lambda configuration
aws lambda get-function-configuration \
  --function-name "fsxn-${VENDOR}-integration-shipper" > "$OUTPUT_DIR/lambda-config.json" 2>/dev/null

echo "Evidence collected in: $OUTPUT_DIR"
```

## Audit Preparation Timeline

| Weeks Before Audit | Action |
|-------------------|--------|
| 8 weeks | Identify applicable framework and controls |
| 6 weeks | Run evidence collection script |
| 4 weeks | Fill in checklist, identify gaps |
| 3 weeks | Remediate gaps (missing alarms, retention, etc.) |
| 2 weeks | Re-run evidence collection, verify completeness |
| 1 week | Package evidence, prepare walkthrough |
| Audit day | Present evidence with architecture context |

## Related Documents

- [Data Classification Guide](data-classification.md)
- [Retention Policy Matrix](retention-policy-matrix.md)
- [Pipeline SLO](pipeline-slo.md)
- [Security Review Checklist](security-review-checklist.md)
- [Governance & Compliance](governance-and-compliance.md)
- [Runbooks](runbooks/)
