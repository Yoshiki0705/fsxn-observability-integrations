# Deployment Guide — Integrating with Existing FSx for ONTAP Environments

🌐 [日本語](../ja/deployment-guide.md) | **English** (this page)

## Purpose

This guide helps you deploy the observability and security stacks from this project into an environment where Amazon FSx for NetApp ONTAP already exists. Every template in this project is an **overlay** — none create FSx file systems, SVMs, or volumes. You bring your existing infrastructure; the templates add observability, incident response, and data protection capabilities on top.

## What You Need Before Starting

Gather the following from your existing environment:

| # | Resource | Where to Find | Used By |
|---|----------|---------------|---------|
| 1 | FSx File System ID | FSx Console → File systems → `fs-xxxxxxxxxxxxxxxxx` | `fsxn-audit-config`, `restore-verification` |
| 2 | Management Endpoint IP | FSx Console → File system details → Management DNS/IP | `automated-response`, `restore-verification`, `fpolicy-apigw`, `lakehouse-monitoring` |
| 3 | SVM Name | FSx Console → Storage virtual machines | `automated-response`, `automated-response-ttl` |
| 4 | SVM ID | FSx Console → SVM details → `svm-xxxxxxxxxxxxxxxxx` | `fsxn-audit-config` |
| 5 | VPC ID | VPC Console | All VPC-mode stacks |
| 6 | Private Subnet IDs | VPC Console → Subnets (same AZ as FSx ENIs) | All VPC-mode stacks |
| 7 | Security Group ID | SG that allows HTTPS (443) to FSx management IP | All VPC-mode stacks |
| 8 | Route Table IDs | VPC Console → Route tables → associated with subnets | `restore-verification`, `content-classification-scanner` |
| 9 | ONTAP Admin Credentials Secret ARN | Secrets Manager → `arn:aws:secretsmanager:...` | `automated-response`, `restore-verification` |
| 10 | S3 Access Point ARN | S3 Console or `aws fsx describe-data-repository-associations` | `prerequisites`, vendor stacks |

## Stack Catalog

### Tier 1: Audit Log Shipping (Vendor Integrations)

These stacks ship FSx for ONTAP audit logs to observability vendors. They are the simplest to deploy — no VPC configuration required when Lambda runs outside VPC.

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Prerequisites | `shared/templates/prerequisites.yaml` | FsxS3AccessPointArn | No |
| S3 Access Point | `shared/templates/s3-access-point.yaml` | BucketName, VpcId (optional) | No |
| Vendor (×10) | `integrations/<vendor>/template.yaml` | FsxS3AccessPointArn, VendorSecretArn | No (default) |

### Tier 2: Incident Response

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Automated Response | `shared/templates/automated-response.yaml` | OntapMgmtIp, Secret ARN, VPC/Subnet/SG, DefaultSvmName | Yes |
| TTL Auto-Unblock | `shared/templates/automated-response-ttl.yaml` | Same as above + BlockTtlMinutes, CheckIntervalMinutes | Yes |

### Tier 3: Data Protection & Classification

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Restore Verification | `shared/templates/restore-verification.yaml` | OntapMgmtIp, FileSystemId, Secret ARN, VPC, Subnet, SG, Route Tables | Yes |
| Content Classification | `shared/templates/content-classification-scanner.yaml` | VpcId (optional), LanguageCode | No (default) |

### Tier 4: Advanced Monitoring

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Syslog → CloudWatch | `shared/templates/syslog-vpce-cloudwatch.yaml` | VpcId, SubnetIds, VpcCidr | Yes |
| FPolicy Server | `shared/templates/fpolicy-server-fargate.yaml` | VpcId, SubnetIds, FsxnSvmSecurityGroupId, ContainerImage | Yes |
| CloudWatch Log Alarm | `shared/templates/cloudwatch-log-alarm.yaml` | LogGroupName, TargetPattern | No |
| Lakehouse Monitoring | `shared/templates/lakehouse-monitoring.yaml` | OntapMgmtEndpoint, S3AccessPointArn, VPC/Subnet/SG | Yes |

### Tier 5: Operational Add-ons

| Stack | Template | Purpose |
|-------|----------|---------|
| Object Ledger | `shared/templates/object-ledger.yaml` | DynamoDB per-file processing state |
| SQS Buffering | `shared/templates/sqs-buffering.yaml` | SQS buffer + DLQ for high-volume |
| Secrets Rotation | `shared/templates/secrets-rotation-sample.yaml` | Auto-rotate vendor API keys |
| PagerDuty Escalation | `shared/templates/pagerduty-escalation.yaml` | Alert routing to PagerDuty |

---

## VPC Endpoint Conflict Matrix

Multiple stacks can create VPC Endpoints. Understanding the two types of conflicts is critical:

- **Interface Endpoints** (SecretsManager, SNS, STS, Comprehend): A second Interface Endpoint for the same service with `PrivateDnsEnabled=true` in the same VPC fails with `"private-dns-enabled cannot be set because there is already a conflicting DNS domain"`. This is the most common deployment failure.
- **Gateway Endpoints** (S3, DynamoDB): These do not conflict via DNS, but you cannot attach the same Gateway Endpoint service to the same route table twice. If an S3 Gateway EP already exists on your route tables, a second one for the same route tables fails.

Use this matrix to set `CreateXxxEndpoint=false` when an endpoint already exists.

| Service | Type | automated-response | restore-verification | content-classification | syslog-vpce | vpc-endpoints |
|---------|------|:------------------:|:--------------------:|:----------------------:|:-----------:|:-------------:|
| **SecretsManager** | Interface | `CreateVpcEndpoints` | `CreateSecretsManagerEndpoint` | — | — | Always |
| **SNS** | Interface | `CreateVpcEndpoints` | — | `CreateVpcEndpoints` | — | — |
| **STS** | Interface | — | `CreateStsEndpoint` | — | — | — |
| **Comprehend** | Interface | — | — | `CreateVpcEndpoints` | — | — |
| **CW Logs Syslog** | Interface | — | — | — | Always | — |
| **S3** | Gateway | — | `CreateS3GatewayEndpoint` | `CreateVpcEndpoints` | — | Always |
| **DynamoDB** | Gateway | — | — | `CreateVpcEndpoints` | — | — |

### How to Check Existing Endpoints

```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" \
  --query 'VpcEndpoints[].{Service:ServiceName,Type:VpcEndpointType,State:State}' \
  --output table
```

### Decision Rule

For each stack you deploy:
1. Run the check above
2. For each endpoint the stack would create, check if that service already exists in the table
3. If it exists → set the corresponding `Create*Endpoint=false`
4. If it does not exist → leave as `true` (default)

---

## Verified Deployment Paths

### Path 1: Audit Log Shipping (Simplest)

**Goal**: Ship FSx for ONTAP audit logs to your observability vendor.

```
s3-access-point.yaml → prerequisites.yaml → integrations/<vendor>/template.yaml
```

**Steps**:
1. Enable audit logging on your SVM (ONTAP CLI: `vserver audit create`)
2. Create an S3 bucket for log delivery
3. Deploy `s3-access-point.yaml` (creates the AP for Lambda to read logs)
4. Deploy `prerequisites.yaml` (EventBridge scheduler, checkpoint table)
5. Deploy vendor template (e.g., `integrations/datadog/template.yaml`)

**No VPC configuration required.** Lambda deploys outside VPC by default.

### Path 2: Incident Response

**Goal**: Automated user/IP blocking with TTL-based auto-unblock.

```
automated-response.yaml (CreateVpcEndpoints=true)
  → automated-response-ttl.yaml
```

**Steps**:
1. Store ONTAP admin credentials in Secrets Manager
2. Deploy `automated-response.yaml` with your VPC/Subnet/SG
3. Deploy Lambda Layer (`shared/lambda-layers/`) and update the function
4. Deploy `automated-response-ttl.yaml` with the same VPC parameters

**Security note**: The Lambda runs inside the VPC to reach the ONTAP management IP directly. VPC Endpoints for Secrets Manager and SNS are created by the first stack.

### Path 3: Recovery Point Verification

**Goal**: Verify snapshots are clean before restoring (ransomware indicator scan).

```
automated-response.yaml (first, creates SecretsManager EP)
  → restore-verification.yaml (CreateSecretsManagerEndpoint=false)
```

**Prerequisites specific to this path**:
- Target volume must be **UNIX security style** (check: `volume show -fields security-style`)
- Target SVM must have **no ONTAP-native S3 server** enabled (check: `vserver object-store-server show`)
- Route Table IDs for your subnets must be provided

**Steps**:
1. Verify prerequisites (run `preflight-check.sh --profile restore-verification`)
2. Deploy `automated-response.yaml` if not already deployed
3. Deploy `restore-verification.yaml` with `CreateSecretsManagerEndpoint=false`
4. Invoke the Step Functions workflow with snapshot details

### Path 4: Content Classification (PII Scanner)

**Goal**: Scan files on FSx for ONTAP volumes for PII using Amazon Comprehend.

```
content-classification-scanner.yaml (VPC外 mode)
```

**Simplest deployment** — leave VpcId empty. Requires an Internet-origin S3 Access Point attached to the target volume.

For VPC-scoped access points (created by restore-verification), set VpcId and disable endpoint creation if they already exist.

### Path 5: Full Suite (All Capabilities)

Deploy in this order to avoid VPC Endpoint conflicts:

| Order | Stack | Endpoint Settings |
|-------|-------|-------------------|
| 1 | `automated-response.yaml` | `CreateVpcEndpoints=true` (creates SecretsManager + SNS) |
| 2 | `automated-response-ttl.yaml` | No endpoints created |
| 3 | `restore-verification.yaml` | `CreateSecretsManagerEndpoint=false`, `CreateStsEndpoint=true`, `CreateS3GatewayEndpoint=false` (if S3 GW EP exists) |
| 4 | `content-classification-scanner.yaml` | Deploy in **VPC-外 mode** (VpcId='') for simplicity |
| 5 | `syslog-vpce-cloudwatch.yaml` | Always creates CW Logs Syslog EP (unique, no conflict) |

---

## Pre-flight Validation

Before deploying VPC-mode stacks, run the pre-flight check script:

```bash
bash shared/scripts/preflight-check.sh \
  --vpc-id vpc-0123456789abcdef0 \
  --profile automated-response

# Available profiles:
#   audit-shipping        — Path 1
#   automated-response    — Path 2
#   restore-verification  — Path 3
#   content-classification — Path 4
#   full-suite            — Path 5
```

The script checks:
- Existing VPC Endpoints (prevents duplicate creation failures)
- Security Group egress rules (HTTPS 443 to ONTAP management IP)
- Route Table associations for specified subnets
- ONTAP S3 server presence on target SVM (restore-verification only)
- S3 Access Point network origin (Internet vs VPC)

---

## Parameter File Templates

Sample parameter files are in `cfn-params/` using the standard CloudFormation JSON format:

```
cfn-params/
├── README.md                              ← Usage instructions
├── automated-response.example.json
├── automated-response-ttl.example.json
├── restore-verification.example.json
├── content-classification.example.json
└── vendor-datadog.example.json
```

Copy, rename (remove `.example`), fill in your values, then deploy:

```bash
cp cfn-params/automated-response.example.json cfn-params/automated-response.json
# Edit with your values

# Option A: create-stack (supports file:// parameter files)
aws cloudformation create-stack \
  --stack-name fsxn-automated-response \
  --template-body file://shared/templates/automated-response.yaml \
  --parameters file://cfn-params/automated-response.json \
  --capabilities CAPABILITY_NAMED_IAM

# Option B: deploy (inline Key=Value only — no file:// support)
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=198.51.100.10 \
    OntapCredentialsSecretArn=arn:aws:secretsmanager:... \
    VpcId=vpc-xxx SubnetIds=subnet-aaa,subnet-bbb \
    SecurityGroupId=sg-xxx DefaultSvmName=svm-prod \
    CreateVpcEndpoints=true \
  --capabilities CAPABILITY_NAMED_IAM
```

**Operational note**: `aws cloudformation deploy --parameter-overrides` does **not** support `file://`. Use inline `Key=Value` pairs with `deploy`, or use `create-stack --parameters file://` for JSON file-based deployment.

---

## Deployment Time Estimates

| Path | Stacks | Estimated Duration | Notes |
|------|--------|--------------------|-------|
| 1: Audit Log Shipping | 3 | 5–10 minutes | No VPC Endpoints to create |
| 2: Incident Response | 2 | 8–15 minutes | Interface EP creation: ~2 min each |
| 3: Recovery Point Verification | 2 | 10–20 minutes | STS EP creation adds time |
| 4: Content Classification | 1 | 3–5 minutes (VPC外) | VPC mode adds 5–10 min for EPs |
| 5: Full Suite | 5 | 25–40 minutes | Deploy sequentially |

**Operational note**: Step Functions execution for restore-verification (Path 3) takes an additional 15–40 minutes per run due to FSx for ONTAP internal synchronization when attaching an S3 Access Point to a FlexClone.

---

## Cost Considerations

### VPC Endpoints (Fixed Monthly)

| Endpoint Type | Cost (per endpoint) | Notes |
|---------------|--------------------:|-------|
| Interface (SecretsManager, SNS, STS, Comprehend) | ~$7.20/month + $0.01/GB | Per-AZ ENI charge |
| Gateway (S3, DynamoDB) | Free | No hourly or data charges |

**Full Suite baseline** (4 Interface EPs × 2 AZs): ~$57.60/month before any data processing.

### Compute and API Costs (Usage-Based)

| Service | Pricing | Typical Monthly (light usage) |
|---------|---------|------------------------------:|
| Lambda (audit polling, 5-min schedule) | $0.20/1M requests + compute | $1–5 |
| Lambda (incident response, event-driven) | Same | < $1 |
| Step Functions (restore-verification) | $0.025/1K transitions | < $1 |
| Comprehend DetectPiiEntities | $0.0001/unit (100 chars) | Varies by scan volume |
| DynamoDB (checkpoint/ledger) | Pay-per-request | < $1 |
| EventBridge Scheduler | $1/1M invocations | < $1 |
| SNS notifications | $0.50/1M publishes | < $1 |

**Cost note**: The largest variable cost is Comprehend PII scanning (content-classification). Scanning 10,000 files averaging 10 KB each costs approximately $10 per scan run.

### Cost Optimization

- Deploy only the paths you need (don't deploy Full Suite if you only need audit shipping)
- Use Gateway EPs (S3, DynamoDB) instead of Interface EPs where possible — they are free
- Set `DefaultMaxFiles` in content-classification to cap per-invocation Comprehend costs
- VPC外 mode for content-classification eliminates the need for 4 additional VPC Endpoints

### Data Processing Consideration (Content Classification)

When using the content-classification-scanner, file contents from FSx for ONTAP volumes are sent to the Amazon Comprehend `DetectPiiEntities` API for analysis. Comprehend processes data within the same AWS Region and does not store it after processing. However, if your organization has data residency or classification policies that restrict sending file contents to AWS AI services, review this with your compliance team before enabling PII scanning on sensitive volumes.

---

## ONTAP Version Requirements

| Feature | Minimum ONTAP Version | FSx for ONTAP Support |
|---------|----------------------|----------------------|
| REST API (all stacks) | 9.6+ | All FSx for ONTAP versions |
| S3 Access Point (restore-verification, classification) | 9.11.1+ | Supported since launch (9.11.1+) |
| Audit logging (NAS) | 9.0+ | All FSx for ONTAP versions |
| Name-mapping (automated-response) | 9.0+ | All FSx for ONTAP versions |
| FPolicy (external server) | 9.0+ | All FSx for ONTAP versions |

FSx for ONTAP currently runs ONTAP 9.11.1 or later, so all features in this project are supported on any FSx for ONTAP file system.

---

## Existing Infrastructure Constraints

### ONTAP S3 Server Exclusivity (restore-verification only)

FSx for ONTAP S3 Access Points and ONTAP-native S3 servers are mutually exclusive on the same SVM. If your SVM has an ONTAP S3 server enabled (for any purpose), the `restore-verification` stack's FlexClone + S3 AP attach step will fail with:

> Amazon FSx is unable to create an S3 access point because of an existing ONTAP object storage server on SVM {svm}

**Resolution**: Use a different SVM without an ONTAP S3 server, or disable the existing server (data loss risk — confirm with team first).

### Volume Security Style (restore-verification only)

The S3 Access Point requires UNIX security style for the target volume. NTFS and mixed volumes are not supported for direct S3 AP attachment.

**Check**: `curl -sk -u admin:pass "https://<mgmt-ip>/api/storage/volumes?name=<vol>&fields=nas.security_style"`

### Active Directory Integration

No stack in this project creates or modifies AD configurations. The `automated-response` stack's SMB user blocking (name-mapping) operates at the ONTAP SVM level and does not require AD changes. However:

- Blocked users are identified by `DOMAIN\\username` pattern
- The domain name must match what ONTAP uses (check: `vserver cifs show`)
- Group-based blocking is not supported (individual users only)

### DNS / Route 53

No stack creates Route 53 records. VPC Endpoint private DNS is handled automatically by AWS (PrivateDnsEnabled=true). No custom DNS configuration required.

---

## Troubleshooting

### Stack rollback: "private-dns-enabled cannot be set"

**Cause**: You are creating a VPC Endpoint that already exists in the VPC.

**Fix**: Set the corresponding `Create*Endpoint=false` parameter. Use the VPC Endpoint check command above.

### Lambda timeout accessing ONTAP management IP

**Cause**: Security Group does not allow outbound HTTPS (443) to the management IP, or Lambda is not in a subnet with a route to the management IP.

**Fix**: Ensure SecurityGroupId allows egress to OntapMgmtIp:443. Verify SubnetIds are in the same VPC as FSx.

### AccessDeniedException on Secrets Manager

**Cause**: Either (a) Secret ARN has changed (Secrets Manager assigns a new random suffix when recreated), or (b) VPC Endpoint for Secrets Manager is not available.

**Fix**: Verify the exact ARN: `aws secretsmanager describe-secret --secret-id <name> --query ARN`. Update the stack with the correct ARN.

### restore-verification: "existing ONTAP object storage server"

**Cause**: The target SVM has an ONTAP S3 server. This is a structural conflict, not a timing issue — no amount of retry will resolve it.

**Fix**: Use a different SVM or delete the ONTAP S3 server (confirm no data loss first).

---

## Day 2: Verification and Ongoing Operations

After deployment, verify the stacks are working correctly:

### Immediate Verification (within 1 hour)

| Path | Verification Step | Expected Result |
|------|-------------------|-----------------|
| 1 (Audit) | Perform a file operation on the audited share, wait 5–10 min | Logs appear in vendor platform (`source:fsxn` in Datadog) |
| 2 (Response) | Send `health_check` via SNS trigger | Lambda returns `"status": "healthy"` |
| 3 (Recovery) | Execute Step Functions with a test snapshot | Workflow completes with `verdict: clean` or `suspicious` |
| 4 (Classification) | Invoke Lambda with a test S3 AP ARN | DynamoDB table contains scan results |

### Ongoing Monitoring

Set up alarms for these CloudWatch metrics:

| Metric | Alarm Condition | Action |
|--------|----------------|--------|
| Lambda Errors (all stacks) | > 0 for 5 minutes | Investigate via CloudWatch Logs |
| DLQ ApproximateNumberOfMessagesVisible | > 0 | Replay failed messages (see [DLQ Replay Runbook](runbooks/dlq-replay.md)) |
| Lambda Duration (audit poller) | > 80% of timeout | Increase LambdaTimeout or LambdaMemorySize |
| Step Functions ExecutionsFailed | > 0 | Check execution history in console |

### Periodic Reviews (Monthly)

- **ProtectedAccountsExtra**: Review the list of accounts that cannot be auto-blocked. Service accounts change over time; stale entries accumulate and reduce the effectiveness of incident response.
- **Secret ARN validity**: If Secrets Manager secrets are rotated or recreated, the ARN suffix changes. Verify with `aws secretsmanager describe-secret --secret-id <name> --query ARN`.
- **VPC Endpoint costs**: Review Interface EP costs; remove any that are no longer needed.

---

## Rollback and Cleanup

### Automatic Rollback

CloudFormation automatically rolls back on deployment failure. No manual intervention required for the stack itself. However:

- VPC Endpoints created before the failure point **are cleaned up** by the rollback
- DynamoDB tables with `DeletionPolicy: Retain` may survive (check with `aws dynamodb list-tables`)
- If a stack enters `ROLLBACK_COMPLETE` state, delete it before re-creating with the same name: `aws cloudformation delete-stack --stack-name <name>`

### Manual Cleanup (Full Removal)

Use the vendor-specific cleanup scripts or the shared cleanup utility:

```bash
# Single vendor stack
bash integrations/<vendor>/scripts/cleanup.sh --all -y

# Shared stacks (delete in reverse deployment order)
aws cloudformation delete-stack --stack-name fsxn-content-classification
aws cloudformation delete-stack --stack-name fsxn-restore-verification
aws cloudformation delete-stack --stack-name fsxn-automated-response-ttl
aws cloudformation delete-stack --stack-name fsxn-automated-response
```

**Operational note**: Delete stacks in reverse deployment order. The `automated-response` stack creates VPC Endpoints used by other stacks; deleting it first causes other stacks to lose Secrets Manager access during their own deletion (usually harmless but generates error logs).

---

## Related Documents

- [Prerequisites and Resource Deployment](prerequisites.md) — S3 bucket, audit logging, S3 AP creation
- [Quick Start (Minimum Test)](quick-start-minimum.md) — Fastest path to verify log delivery
- [Verified Recovery Point Guide](verified-recovery-point-guide.md) — Detailed restore-verification usage
- [Automated Response Guide](automated-response-guide.md) — Incident response operations
- [Multi-Account Deployment](multi-account-deployment.md) — StackSets for organizations
