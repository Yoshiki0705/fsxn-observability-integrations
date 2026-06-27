# FSx for ONTAP Management Console — Setup Guide

This guide covers the deployment, configuration, and maintenance of the FSx for ONTAP Management Console. The console provides a self-hosted observability and management solution for Amazon FSx for NetApp ONTAP, combining Harvest metrics collection with a ToolJet-based management UI.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment](#deployment)
3. [Parameter Reference](#parameter-reference)
4. [Post-Deployment Verification](#post-deployment-verification)
5. [Troubleshooting](#troubleshooting)
6. [Cleanup](#cleanup)
7. [Updates](#updates)

---

## Prerequisites

Before deploying the Management Console, ensure the following resources are available in your AWS account.

### 1. VPC and Subnets

| Resource | Requirement |
|----------|-------------|
| VPC | Existing VPC with DNS resolution enabled |
| Private Subnets | At least 2 subnets in different Availability Zones (for ECS Fargate tasks) |
| Public Subnets | At least 2 subnets in different Availability Zones (for ALB and NAT Gateway) |

> **Note**: The deployment creates a NAT Gateway in one of the public subnets. ECS Fargate tasks are placed exclusively in private subnets.

### 2. Amazon FSx for NetApp ONTAP

| Resource | Requirement |
|----------|-------------|
| File System | FSx for ONTAP file system in the same VPC |
| Management Endpoint | Management endpoint IP or DNS name (port 443 accessible from private subnets) |
| Admin Credentials | `fsxadmin` username and password |
| S3 Access Point | (Optional) S3 Access Point for file browsing functionality |

### 3. AWS Secrets Manager Secret

Store the ONTAP admin credentials in Secrets Manager with the following JSON format:

```json
{
  "username": "fsxadmin",
  "password": "<your-ontap-admin-password>"
}
```

Create the secret:

```bash
aws secretsmanager create-secret \
  --name fsxn-mgmt-ontap-credentials \
  --description "ONTAP admin credentials for FSx for ONTAP Management Console" \
  --secret-string '{"username":"fsxadmin","password":"<your-password>"}'
```

Note the ARN from the output — you will need it as the `OntapCredentialsSecretArn` parameter.

### 4. ACM Certificate

An ACM certificate is required for HTTPS on the Application Load Balancer.

```bash
# Request a certificate (DNS validation recommended)
aws acm request-certificate \
  --domain-name "fsxn-mgmt.example.com" \
  --validation-method DNS

# Or use an existing certificate — note the ARN
aws acm list-certificates --query "CertificateSummaryList[?DomainName=='fsxn-mgmt.example.com'].CertificateArn"
```

### 5. FSx for ONTAP Security Group

The FSx for ONTAP file system's security group ID is required so that the deploy script can automatically add ingress rules allowing Harvest and ToolJet to access the management endpoint on port 443.

```bash
# Find the FSx for ONTAP security group ID
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=*FSx*" \
  --query "NetworkInterfaces[0].Groups[0].GroupId" \
  --output text
```

Set as environment variable:
```bash
export FSXN_SECURITY_GROUP_ID="sg-0123456789abcdef0"
```

If not set, you must manually add security group rules after deployment (see [Troubleshooting](#fsx-ontap-security-group-rules)).

### 5. (Optional) Amazon Cognito User Pool

If you want to use an existing Cognito User Pool, note the following values:
- User Pool ID (e.g., `ap-northeast-1_AbCdEfGhI`)
- App Client ID
- Cognito Domain prefix

If not provided, the auth stack (Stack 2) creates a new User Pool.

---

## Deployment

The Management Console consists of 5 CloudFormation stacks deployed in dependency order. The `deploy.sh` script orchestrates the entire process.

### Stack Deployment Order

```
1. fsxn-mgmt-network       — VPC Endpoints, NAT Gateway, Security Groups
2. fsxn-mgmt-auth          — Cognito User Pool, App Client
3. fsxn-mgmt-observability — AMP, AMG, Harvest ECS, ADOT Sidecar
4. fsxn-mgmt-console       — ToolJet ECS, ALB, RDS, S3 Copy Lambda
5. fsxn-mgmt-monitoring    — CloudWatch Alarms, Dashboard, SNS
```

### Step 1: Set Environment Variables

```bash
export AWS_REGION="ap-northeast-1"
export VPC_ID="vpc-0123456789abcdef0"
export PRIVATE_SUBNET_IDS="subnet-aaaa,subnet-bbbb"
export PUBLIC_SUBNET_IDS="subnet-cccc,subnet-dddd"
export ONTAP_MGMT_ENDPOINT="<management-ip>"
export ONTAP_CREDENTIALS_SECRET_ARN="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fsxn-mgmt-ontap-credentials-XXXXXX"
export ACM_CERTIFICATE_ARN="arn:aws:acm:ap-northeast-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export S3_ACCESS_POINT_ARN="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-file-ap"
export MFA_CONFIGURATION="OPTIONAL"
export SESSION_DURATION_HOURS="8"
export HARVEST_IMAGE_TAG="24.05.2"
export TOOLJET_IMAGE_TAG="latest"
```

### Step 2: Run the Deployment Script

```bash
cd management-console
bash scripts/deploy.sh
```

The script performs the following:
1. Validates that all required environment variables are set
2. Deploys each stack in dependency order
3. Passes outputs from earlier stacks as parameters to later stacks
4. Exits with a non-zero code if any stack fails

### Step 3: Manual Deployment (Alternative)

If you prefer to deploy stacks individually:

```bash
# Stack 1: Network
aws cloudformation deploy \
  --template-file templates/network.yaml \
  --stack-name fsxn-mgmt-network \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    PrivateSubnetIds="${PRIVATE_SUBNET_IDS}" \
    PublicSubnetIds="${PUBLIC_SUBNET_IDS}" \
    OntapManagementEndpoint="${ONTAP_MGMT_ENDPOINT}" \
  --capabilities CAPABILITY_NAMED_IAM

# Stack 2: Auth
aws cloudformation deploy \
  --template-file templates/auth.yaml \
  --stack-name fsxn-mgmt-auth \
  --parameter-overrides \
    MfaConfiguration="${MFA_CONFIGURATION}" \
    SessionDurationHours="${SESSION_DURATION_HOURS}" \
  --capabilities CAPABILITY_NAMED_IAM

# Stack 3: Observability
aws cloudformation deploy \
  --template-file templates/observability.yaml \
  --stack-name fsxn-mgmt-observability \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    PrivateSubnetIds="${PRIVATE_SUBNET_IDS}" \
    OntapManagementEndpoint="${ONTAP_MGMT_ENDPOINT}" \
    OntapCredentialsSecretArn="${ONTAP_CREDENTIALS_SECRET_ARN}" \
    CognitoUserPoolId="<output-from-stack-2>" \
    HarvestImageTag="${HARVEST_IMAGE_TAG}" \
  --capabilities CAPABILITY_NAMED_IAM

# Stack 4: Console
aws cloudformation deploy \
  --template-file templates/console.yaml \
  --stack-name fsxn-mgmt-console \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    PrivateSubnetIds="${PRIVATE_SUBNET_IDS}" \
    PublicSubnetIds="${PUBLIC_SUBNET_IDS}" \
    OntapManagementEndpoint="${ONTAP_MGMT_ENDPOINT}" \
    OntapCredentialsSecretArn="${ONTAP_CREDENTIALS_SECRET_ARN}" \
    CognitoUserPoolId="<output-from-stack-2>" \
    CognitoAppClientId="<output-from-stack-2>" \
    CognitoDomain="<output-from-stack-2>" \
    ToolJetImageTag="${TOOLJET_IMAGE_TAG}" \
    S3AccessPointArn="${S3_ACCESS_POINT_ARN}" \
    SessionDurationHours="${SESSION_DURATION_HOURS}" \
  --capabilities CAPABILITY_NAMED_IAM

# Stack 5: Monitoring
aws cloudformation deploy \
  --template-file templates/monitoring.yaml \
  --stack-name fsxn-mgmt-monitoring \
  --parameter-overrides \
    AlertSnsTopicArn="" \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## Parameter Reference

All 14 parameters used across the 5 CloudFormation stacks:

| # | Parameter | Type | Required | Default | Description |
|---|-----------|------|----------|---------|-------------|
| 1 | `VpcId` | `AWS::EC2::VPC::Id` | Yes | — | Target VPC for all resources |
| 2 | `PrivateSubnetIds` | `List<AWS::EC2::Subnet::Id>` | Yes | — | Private subnets (2+ AZs) for ECS tasks and Lambda |
| 3 | `PublicSubnetIds` | `List<AWS::EC2::Subnet::Id>` | Yes | — | Public subnets (2+ AZs) for ALB and NAT Gateway |
| 4 | `OntapManagementEndpoint` | `String` | Yes | — | FSx for ONTAP management IP or DNS name |
| 5 | `OntapCredentialsSecretArn` | `String` | Yes | — | Secrets Manager ARN for ONTAP credentials |
| 6 | `CognitoUserPoolId` | `String` | Yes | — | Cognito User Pool ID (created by auth stack) |
| 7 | `CognitoAppClientId` | `String` | Yes | — | Cognito App Client ID (created by auth stack) |
| 8 | `CognitoDomain` | `String` | Yes | — | Cognito hosted UI domain prefix |
| 9 | `HarvestImageTag` | `String` | Yes | `latest` | NetApp Harvest container image tag |
| 10 | `ToolJetImageTag` | `String` | Yes | `latest` | ToolJet container image tag |
| 11 | `S3AccessPointArn` | `String` | Yes | — | FSx for ONTAP S3 Access Point ARN |
| 12 | `MfaConfiguration` | `String` | Yes | `OPTIONAL` | MFA mode: `OFF` / `OPTIONAL` / `REQUIRED` |
| 13 | `SessionDurationHours` | `Number` | Yes | `8` | Session duration (1–12 hours) |
| 14 | `AlertSnsTopicArn` | `String` | No | `""` | SNS topic ARN for alarms (empty = create new) |

### Stack-to-Parameter Mapping

| Parameter | network | auth | observability | console | monitoring |
|-----------|:-------:|:----:|:------------:|:-------:|:----------:|
| VpcId | ✓ | | ✓ | ✓ | |
| PrivateSubnetIds | ✓ | | ✓ | ✓ | |
| PublicSubnetIds | ✓ | | | ✓ | |
| OntapManagementEndpoint | ✓ | | ✓ | ✓ | |
| OntapCredentialsSecretArn | | | ✓ | ✓ | |
| CognitoUserPoolId | | | ✓ | ✓ | |
| CognitoAppClientId | | | | ✓ | |
| CognitoDomain | | | | ✓ | |
| HarvestImageTag | | | ✓ | | |
| ToolJetImageTag | | | | ✓ | |
| S3AccessPointArn | | | | ✓ | |
| MfaConfiguration | | ✓ | | | |
| SessionDurationHours | | ✓ | | ✓ | |
| AlertSnsTopicArn | | | | | ✓ |

---

## Cost Estimate

| Resource | Unit Price | Monthly (24/7) | Notes |
|----------|-----------|----------------|-------|
| NAT Gateway | $0.062/h + $0.062/GB | ~$45 | Depends on data transfer |
| ECS Fargate (Harvest + ADOT) | ~$0.05/h | ~$36 | 1024 CPU / 2048 MB |
| ECS Fargate (Appsmith/ToolJet) | ~$0.05/h | ~$36 | 1024 CPU / 2048 MB |
| RDS db.t3.medium | $0.068/h | ~$49 | State management |
| VPC Interface Endpoints x5 | $0.014/h each | ~$50 | SM, CW Logs, ECR x2, STS |
| AMP | $0.003/10K samples | ~$5 | Depends on metrics volume |
| AMG | $9/editor/month | $9 | Viewers are free |
| ALB | $0.0225/h + LCU | ~$20 | Depends on request volume |
| **Total** | | **~$250/month** | Full 24/7 operation estimate |

> ⚠️ This is a **sizing reference**, not a guaranteed price. Actual costs vary by usage, region, and data transfer. VPC-origin S3 APs eliminate the NAT Gateway (~$45/month savings). Use [AWS Pricing Calculator](https://calculator.aws/) for precise estimates.

---

## Post-Deployment Verification

### 1. ALB Access

Retrieve the ALB DNS name from the console stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-mgmt-console \
  --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" \
  --output text
```

Open `https://<alb-dns-name>` in your browser. You should be redirected to the Cognito login page.

### 2. Grafana Dashboards

After logging in, navigate to the Grafana workspace:

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-mgmt-observability \
  --query "Stacks[0].Outputs[?OutputKey=='AmgWorkspaceUrl'].OutputValue" \
  --output text
```

Verify that:
- AMP data source is configured and connected
- Harvest dashboards are imported (20+ dashboards across 5 categories)
- Metrics are flowing (check volume performance dashboard for recent data)

### 3. ToolJet Login

Access the ToolJet management UI at `https://<alb-dns-name>/app/`:

1. Log in with your Cognito credentials
2. Verify the ONTAP REST API data source is connected (Settings → Data Sources)
3. Test a basic operation (e.g., list volumes)

### 4. ECS Service Health

```bash
# Check Harvest service
aws ecs describe-services \
  --cluster fsxn-mgmt-cluster \
  --services fsxn-mgmt-harvest \
  --query "services[0].{status:status,running:runningCount,desired:desiredCount}"

# Check ToolJet service
aws ecs describe-services \
  --cluster fsxn-mgmt-cluster \
  --services fsxn-mgmt-tooljet \
  --query "services[0].{status:status,running:runningCount,desired:desiredCount}"
```

### 5. CloudWatch Dashboard

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-mgmt-monitoring \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" \
  --output text
```

Open the dashboard URL and verify all widgets display data.

---

## Troubleshooting

### Stack Creation Failures

#### `CREATE_FAILED` — VPC/Subnet Validation

**Symptom**: Network stack fails with subnet validation error.

**Cause**: Subnets do not span at least 2 Availability Zones, or subnet IDs are invalid.

**Resolution**:
```bash
# Verify subnets are in different AZs
aws ec2 describe-subnets \
  --subnet-ids subnet-aaaa subnet-bbbb \
  --query "Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,VpcId:VpcId}"
```

#### `CREATE_FAILED` — ECS Task Fails to Start

**Symptom**: Observability or console stack reports ECS service unable to reach steady state.

**Cause**: Container image pull failure, or security group blocks outbound access to ECR.

**Resolution**:
```bash
# Check ECS task stopped reason
aws ecs describe-tasks \
  --cluster fsxn-mgmt-cluster \
  --tasks $(aws ecs list-tasks --cluster fsxn-mgmt-cluster --service-name fsxn-mgmt-harvest --query "taskArns[0]" --output text) \
  --query "tasks[0].stoppedReason"
```

Ensure VPC Endpoints for ECR (API + DKR) are created, or NAT Gateway provides internet access.

#### `CREATE_FAILED` — Secrets Manager Access Denied

**Symptom**: ECS task starts but Harvest cannot connect to ONTAP.

**Cause**: Task IAM role does not have `secretsmanager:GetSecretValue` permission on the specified secret ARN.

**Resolution**: Verify the `OntapCredentialsSecretArn` parameter matches the actual secret ARN (including the random suffix).

#### `CREATE_FAILED` — ALB Certificate Error

**Symptom**: Console stack fails at ALB listener creation.

**Cause**: ACM certificate ARN is invalid or the certificate is not in `ISSUED` state.

**Resolution**:
```bash
aws acm describe-certificate \
  --certificate-arn "${ACM_CERTIFICATE_ARN}" \
  --query "Certificate.Status"
```

Ensure the certificate status is `ISSUED` and the region matches the deployment region.

### Connectivity Issues

#### Harvest Cannot Reach ONTAP

**Symptom**: No metrics in AMP/Grafana after deployment.

**Cause**: Security group does not allow outbound traffic to ONTAP management endpoint on port 443.

**Resolution**:
1. Verify `OntapAccessSG` allows inbound :443 from `HarvestTaskSG`
2. Verify ONTAP management endpoint is reachable from private subnets
3. Check Harvest CloudWatch logs for connection errors:

```bash
aws logs tail /ecs/fsxn-mgmt-harvest --since 30m
```

#### ToolJet Cannot Reach ONTAP REST API

**Symptom**: Volume/SVM operations fail with timeout errors.

**Cause**: Same as above — security group or network routing issue.

**Resolution**: Check `OntapAccessSG` allows inbound :443 from `ToolJetTaskSG`.

### Cognito Authentication Issues

#### Redirect Loop After Login

**Symptom**: Browser enters a redirect loop between ALB and Cognito.

**Cause**: Cognito App Client callback URL does not match the ALB DNS name.

**Resolution**: Verify the App Client callback URL includes `https://<alb-dns-name>/oauth2/idpresponse`.

### Harvest Container Issues

#### Harvest Container Fails to Start — `/bin/sh` not found

**Symptom**: `exec: "/bin/sh": stat /bin/sh: no such file or directory`

**Cause**: The Harvest Docker image (`ghcr.io/netapp/harvest`) does not include `/bin/sh`. However, it does include `/busybox/sh` which can be used as the entrypoint.

**Resolution**:
- Use `/busybox/sh` as the entrypoint (NOT `/bin/sh`)
- The current `templates/observability.yaml` uses `/busybox/sh -c` to write config then exec the poller
- No init container is needed — the Harvest container handles its own config generation

#### Harvest Container Fails to Start — `bin/poller` not found

**Symptom**: `exec: "bin/poller": stat bin/poller: no such file or directory`

**Cause**: The shared volume was mounted at `/opt/harvest`, which overwrites the Harvest binary files (poller, etc.) with an empty volume.

**Resolution**: Do NOT mount volumes at `/opt/harvest`. When using the `/busybox/sh -c` entrypoint pattern, write the config file to `/opt/harvest/harvest.yml` directly (no shared volume needed). The correct CLI syntax is:

```
bin/poller --config harvest.yml -p fsxn-cluster
```

Note: The command is `bin/poller --config` (NOT `start --config`).

#### Security Considerations for ECS Secrets Injection

Credentials injected via the ECS `Secrets` field exist as plaintext environment variables in container memory. This is the standard ECS Fargate pattern, but be aware of the following:

- Memory dump attacks could expose credentials
- Ensure container log levels don't output environment variables (check Harvest/ADOT log configuration)

For higher security requirements, consider calling the Secrets Manager API directly from within the application instead of using ECS Secrets injection.

#### VPC Endpoint DNS Propagation Timing

**Symptom**: `ResourceInitializationError: unable to pull secrets or registry auth: unable to retrieve secret from asm: There is a connection issue between the task and AWS Secrets Manager.`

**Cause**: When VPC Interface Endpoints are created, their private DNS records may take 1-2 minutes to propagate. If the ECS service starts immediately after endpoint creation, tasks cannot reach Secrets Manager.

**Resolution**:
- The ECS deployment circuit breaker will automatically retry failed tasks
- After DNS propagation completes (typically within 2 minutes), subsequent task launches will succeed
- If the circuit breaker triggers before DNS propagates, redeploy the observability stack:

```bash
aws cloudformation deploy --template-file templates/observability.yaml \
  --stack-name fsxn-mgmt-observability \
  --parameter-overrides ... \
  --capabilities CAPABILITY_NAMED_IAM
```

#### FSx for ONTAP Security Group Rules

**Symptom**: Harvest or ToolJet cannot connect to ONTAP management endpoint (timeout or connection refused).

**Cause**: The FSx for ONTAP file system's security group does not allow inbound port 443 from the Harvest/ToolJet task security groups.

**Resolution**: Set `FSXN_SECURITY_GROUP_ID` and re-run deploy, or add the rule manually:

```bash
# Automated (re-run deploy with the env var set)
export FSXN_SECURITY_GROUP_ID="sg-0123456789abcdef0"
bash scripts/deploy.sh

# Manual
aws ec2 authorize-security-group-ingress \
  --group-id <fsx-ontap-sg-id> \
  --protocol tcp --port 443 \
  --source-group <harvest-task-sg-id>
```

#### CloudFormation Stack Deletion Blocked by SG Cross-References

**Symptom**: Network stack enters `DELETE_FAILED` state with error `resource sg-xxx has a dependent object`.

**Cause**: The FSx for ONTAP security group still references the Harvest/ToolJet task security groups. CloudFormation cannot delete a security group that is referenced by another security group.

**Resolution**: Set `FSXN_SECURITY_GROUP_ID` before running cleanup:

```bash
export FSXN_SECURITY_GROUP_ID="sg-0123456789abcdef0"
bash scripts/cleanup.sh
```

The cleanup script will automatically remove the cross-references before deleting the stacks.

---

## Cleanup

The `cleanup.sh` script deletes all 5 stacks in reverse dependency order.

### Run Cleanup

```bash
cd management-console
bash scripts/cleanup.sh
```

### Deletion Order

```
1. fsxn-mgmt-monitoring    (no dependencies)
2. fsxn-mgmt-console       (depends on observability, auth, network)
3. fsxn-mgmt-observability (depends on auth, network)
4. fsxn-mgmt-auth          (depends on network)
5. fsxn-mgmt-network       (base stack)
```

### Manual Cleanup

```bash
# Delete in reverse order
aws cloudformation delete-stack --stack-name fsxn-mgmt-monitoring
aws cloudformation wait stack-delete-complete --stack-name fsxn-mgmt-monitoring

aws cloudformation delete-stack --stack-name fsxn-mgmt-console
aws cloudformation wait stack-delete-complete --stack-name fsxn-mgmt-console

aws cloudformation delete-stack --stack-name fsxn-mgmt-observability
aws cloudformation wait stack-delete-complete --stack-name fsxn-mgmt-observability

aws cloudformation delete-stack --stack-name fsxn-mgmt-auth
aws cloudformation wait stack-delete-complete --stack-name fsxn-mgmt-auth

aws cloudformation delete-stack --stack-name fsxn-mgmt-network
aws cloudformation wait stack-delete-complete --stack-name fsxn-mgmt-network
```

### Handling DELETE_FAILED

If a stack enters `DELETE_FAILED` state:

```bash
# Identify retained resources
aws cloudformation describe-stack-resources \
  --stack-name <failed-stack-name> \
  --query "StackResources[?ResourceStatus=='DELETE_FAILED'].{Type:ResourceType,LogicalId:LogicalResourceId,PhysicalId:PhysicalResourceId}"
```

Common causes:
- **S3 bucket not empty**: Empty the temp bucket before deleting the console stack
- **RDS snapshot**: Delete or skip the final snapshot
- **ENI in use**: Wait for VPC endpoint ENIs to detach (may take a few minutes)

---

## Updates

### Container Image Tag Update

To update Harvest or ToolJet to a new version, change the image tag parameter and redeploy the corresponding stack.

#### Update Harvest

```bash
export HARVEST_IMAGE_TAG="24.11.0"

aws cloudformation deploy \
  --template-file templates/observability.yaml \
  --stack-name fsxn-mgmt-observability \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    PrivateSubnetIds="${PRIVATE_SUBNET_IDS}" \
    OntapManagementEndpoint="${ONTAP_MGMT_ENDPOINT}" \
    OntapCredentialsSecretArn="${ONTAP_CREDENTIALS_SECRET_ARN}" \
    CognitoUserPoolId="<cognito-user-pool-id>" \
    HarvestImageTag="${HARVEST_IMAGE_TAG}" \
  --capabilities CAPABILITY_NAMED_IAM
```

#### Update ToolJet

```bash
export TOOLJET_IMAGE_TAG="v2.50.0"

aws cloudformation deploy \
  --template-file templates/console.yaml \
  --stack-name fsxn-mgmt-console \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    PrivateSubnetIds="${PRIVATE_SUBNET_IDS}" \
    PublicSubnetIds="${PUBLIC_SUBNET_IDS}" \
    OntapManagementEndpoint="${ONTAP_MGMT_ENDPOINT}" \
    OntapCredentialsSecretArn="${ONTAP_CREDENTIALS_SECRET_ARN}" \
    CognitoUserPoolId="<cognito-user-pool-id>" \
    CognitoAppClientId="<cognito-app-client-id>" \
    CognitoDomain="<cognito-domain>" \
    ToolJetImageTag="${TOOLJET_IMAGE_TAG}" \
    S3AccessPointArn="${S3_ACCESS_POINT_ARN}" \
    SessionDurationHours="${SESSION_DURATION_HOURS}" \
  --capabilities CAPABILITY_NAMED_IAM
```

#### Using deploy.sh for Updates

The deploy script also supports updates. Simply change the image tag environment variable and re-run:

```bash
export HARVEST_IMAGE_TAG="24.11.0"
bash scripts/deploy.sh
```

The script uses `aws cloudformation deploy` which performs an update if the stack already exists. Only the changed stack will be updated; other stacks will report "No changes to deploy".

### Update Verification

After updating, verify the new version is running:

```bash
# Check Harvest task image
aws ecs describe-task-definition \
  --task-definition fsxn-mgmt-harvest \
  --query "taskDefinition.containerDefinitions[?name=='harvest'].image"

# Check ToolJet task image
aws ecs describe-task-definition \
  --task-definition fsxn-mgmt-tooljet \
  --query "taskDefinition.containerDefinitions[?name=='tooljet'].image"
```

Confirm the ECS service has completed the rolling update:

```bash
aws ecs describe-services \
  --cluster fsxn-mgmt-cluster \
  --services fsxn-mgmt-harvest fsxn-mgmt-tooljet \
  --query "services[].{name:serviceName,running:runningCount,desired:desiredCount,deployments:length(deployments)}"
```

A successful update shows `deployments: 1` (only the PRIMARY deployment remains).
