# FPolicy PoC Checklist

## Objective

Validate the FPolicy file activity pipeline end-to-end: ONTAP file operation → ECS Fargate → SQS → Lambda → Datadog.

## Preconditions

- [ ] FSx for ONTAP file system deployed (Single-AZ or Multi-AZ)
- [ ] CIFS-enabled SVM with at least one SMB share
- [ ] VPC with private subnets (same as FSx ONTAP)
- [ ] Private subnet egress: NAT Gateway or VPC endpoints (ECR, CloudWatch Logs, SQS)
- [ ] ECR repository with FPolicy server image (`docker buildx build --platform linux/amd64`)
- [ ] Datadog account with API key in Secrets Manager
- [ ] ONTAP fsxadmin credentials accessible (Secrets Manager or direct)
- [ ] Network path from Fargate subnet to FSx ONTAP data LIFs (TCP:9898)

## PoC Scope

### In Scope

- SMB create-event delivery to Datadog
- Fargate TCP listener connectivity
- SQS → Lambda → Datadog shipping
- Fargate task restart and IP update recovery
- Datadog Log Explorer query validation
- End-to-end latency measurement

### Out of Scope

- Full operation coverage guarantee (rename/delete in async mode)
- NFS production readiness
- Multi-AZ HA design
- High-volume performance benchmark
- Audit log replacement
- TLS/mTLS for FPolicy connection

## Validation Steps

### Step 1: Deploy Infrastructure

```bash
# Deploy Fargate stack
aws cloudformation deploy \
  --template-file shared/templates/fpolicy-server-fargate.yaml \
  --stack-name fsxn-fpolicy-server \
  --parameter-overrides \
    VpcId=<vpc-id> SubnetIds=<subnet-id> \
    FsxnSvmSecurityGroupId=<fsx-sg-id> \
    ContainerImage=<ecr-uri>:latest \
  --capabilities CAPABILITY_NAMED_IAM

# Deploy Datadog Lambda
SQS_ARN=$(aws cloudformation describe-stacks --stack-name fsxn-fpolicy-server \
  --query "Stacks[0].Outputs[?OutputKey=='FPolicyQueueArn'].OutputValue" --output text)

aws cloudformation deploy \
  --template-file integrations/datadog/template-ems-fpolicy.yaml \
  --stack-name fsxn-datadog-ems-fpolicy \
  --parameter-overrides \
    DatadogApiKeySecretArn=<secret-arn> DatadogSite=<site> \
    FPolicySqsQueueArn=${SQS_ARN} \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 2: Configure ONTAP FPolicy

```bash
# Get Fargate task IP
TASK_IP=$(aws ecs describe-tasks --cluster fsxn-fpolicy-server-cluster \
  --tasks $(aws ecs list-tasks --cluster fsxn-fpolicy-server-cluster \
    --query "taskArns[0]" --output text) \
  --query "tasks[0].containers[0].networkInterfaces[0].privateIpv4Address" --output text)

# Configure ONTAP (via CLI or REST API)
# See: docs/en/fpolicy-production-architecture-patterns.md
```

### Step 3: Validate Connection

- [ ] ECS CloudWatch Logs show `[+] Connection from`
- [ ] ECS CloudWatch Logs show `[Handshake] Policy=...`
- [ ] ECS CloudWatch Logs show `[KeepAlive] Received`

### Step 4: Validate Event Delivery

- [ ] Create a file on the SMB share
- [ ] ECS logs show `[Event] create <filename>`
- [ ] ECS logs show `[SQS] Sent: <filename> (create)`
- [ ] Lambda CloudWatch Logs show `shipped: 1`
- [ ] Datadog Log Explorer: `source:fsxn-fpolicy` returns the event

### Step 5: Validate Restart Recovery

- [ ] Scale Fargate to 0, then back to 1
- [ ] Update ONTAP engine IP (`fpolicy-update-engine-ip.sh --auto`)
- [ ] Verify reconnection (KeepAlive in logs)
- [ ] Create another file, confirm Datadog delivery

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Create event delivered to Datadog | Within 30 seconds |
| Restart recovery | Within 3 minutes |
| Lambda processing time | < 500ms per event |
| No Lambda errors | 0 errors during PoC |

## Known Limitations (Acknowledge Before Go/No-Go)

- [ ] Rename/delete events may not be delivered in async mode
- [ ] NFS requires explicit version pinning and careful testing
- [ ] User field may be empty for some operations
- [ ] Event loss possible during Fargate task restart (~2 minutes)
- [ ] FPolicy is a real-time signal, not a full audit replacement

## Rollback Procedure

```bash
# 1. Disable FPolicy on ONTAP
# vserver fpolicy disable -vserver <svm> -policy-name fpolicy_aws

# 2. Delete AWS stacks
aws cloudformation delete-stack --stack-name fsxn-datadog-ems-fpolicy
aws cloudformation delete-stack --stack-name fsxn-fpolicy-server
```

## Go / No-Go Decision

| Question | Answer Required |
|----------|----------------|
| Did create events arrive in Datadog? | Yes/No |
| Is the latency acceptable for the use case? | Yes/No |
| Are the known limitations acceptable? | Yes/No |
| Is the cost model understood? | Yes/No |
| Is the production HA design identified? | Yes/No |
