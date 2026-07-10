# FSx for ONTAP Management Console — Phase 2B Guide

🌐 [日本語](../ja/phase2b-guide.md) | **English** (this page)

This guide covers the Phase 2B features added to the FSx for ONTAP Management Console: custom domain support (Route 53 + ACM), role-based access control (RBAC) via Cognito groups, and automated Grafana dashboard provisioning.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Upgrading from Phase 2A](#upgrading-from-phase-2a)
4. [Custom Domain Setup](#custom-domain-setup)
5. [RBAC Configuration](#rbac-configuration)
6. [Dashboard Auto-Provisioning](#dashboard-auto-provisioning)
7. [Troubleshooting](#troubleshooting)

---

## Overview

Phase 2B extends the existing Phase 2A Management Console with three key capabilities:

| Feature | Description |
|---------|-------------|
| Custom Domain | Access the console via your own domain using Route 53 + ACM certificate |
| RBAC | Separate admin and viewer permissions using Cognito groups |
| Dashboard Auto-Provisioning | Automatically import Grafana dashboards during CloudFormation deployment |

### Files Added/Modified

```
management-console/
├── lambda/
│   └── dashboard_importer.py       # Dashboard import Lambda
├── templates/
│   ├── console.yaml                # Route 53 record added (modified)
│   ├── auth.yaml                   # Cognito groups added (modified)
│   └── observability.yaml          # Dashboard import added (modified)
├── tooljet-workflows/
│   └── rbac-helper.json            # RBAC role check helper (new)
├── tests/
│   └── test_dashboard_importer.py  # Unit tests (new)
└── docs/
    ├── ja/phase2b-guide.md         # Japanese guide
    └── en/phase2b-guide.md         # This guide
```

---

## Prerequisites

### Existing Phase 2A Deployment

Phase 2B is an in-place upgrade to Phase 2A. Ensure the following stacks are deployed and healthy:

```
fsxn-mgmt-network
fsxn-mgmt-auth
fsxn-mgmt-observability
fsxn-mgmt-console
fsxn-mgmt-monitoring
```

### Custom Domain Prerequisites (Optional)

If you plan to use a custom domain, prepare the following:

| Resource | Requirement | Notes |
|----------|-------------|-------|
| ACM Certificate | Issued in the same region as the ALB | DNS validation recommended |
| Route 53 Hosted Zone | Public hosted zone for the target domain | Subdomains are supported |
| Domain Name | Managed in Route 53 | e.g., `console.example.com` |

#### Issuing an ACM Certificate

```bash
# Request a certificate (DNS validation)
aws acm request-certificate \
  --domain-name console.example.com \
  --validation-method DNS \
  --region ap-northeast-1

# Note the CertificateArn from the output
# Add the DNS validation record to Route 53 to complete validation
```

#### Finding Your Route 53 Hosted Zone ID

```bash
aws route53 list-hosted-zones-by-name \
  --dns-name example.com \
  --query 'HostedZones[0].Id' --output text
# Output example: /hostedzone/Z0123456789ABCDEFGHIJ
# The hosted zone ID is "Z0123456789ABCDEFGHIJ"
```

### Dashboard Auto-Provisioning Prerequisites (Optional)

| Resource | Requirement | Notes |
|----------|-------------|-------|
| AMG Workspace | Already created | API key generation required |
| AMG API Key | Admin role | Stored in Secrets Manager |

#### Creating and Storing the AMG API Key

```bash
# Create an API key in the AMG console (Admin role)
# Store the generated key in Secrets Manager
aws secretsmanager create-secret \
  --name fsxn-mgmt-grafana-api-key \
  --description "AMG API key for dashboard auto-provisioning" \
  --secret-string '{"api_key": "<your-amg-api-key>"}'
```

---

## Upgrading from Phase 2A

Phase 2B is an **in-place update** to Phase 2A. All existing functionality is preserved.

### New Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CUSTOM_DOMAIN_NAME` | No | Custom domain name (e.g., `console.example.com`) |
| `HOSTED_ZONE_ID` | No* | Route 53 hosted zone ID |
| `ADMIN_EMAIL` | No | Email address for the initial admin user |

> \* If `CUSTOM_DOMAIN_NAME` is set, both `HOSTED_ZONE_ID` and `CERTIFICATE_ARN` are also required.

### Upgrade Steps

#### Step 1: Add Environment Variables

```bash
# Keep all existing Phase 2A variables unchanged

# Custom domain (optional)
export CUSTOM_DOMAIN_NAME="console.example.com"
export HOSTED_ZONE_ID="Z0123456789ABCDEFGHIJ"
export CERTIFICATE_ARN="arn:aws:acm:ap-northeast-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Initial admin user (optional)
export ADMIN_EMAIL="admin@example.com"
```

#### Step 2: Run the Deploy Script

```bash
cd management-console/scripts
bash deploy.sh
```

The deploy script performs the following:
- If `CUSTOM_DOMAIN_NAME` is set, validates that `CERTIFICATE_ARN` and `HOSTED_ZONE_ID` are also present
- Stack 2 (auth): Creates Cognito groups; creates admin user if `ADMIN_EMAIL` is set
- Stack 3 (observability): Uploads dashboard JSONs to S3 and triggers auto-import
- Stack 4 (console): Creates Route 53 record (when custom domain is configured)

#### Step 3: Verify

- Confirm the console is accessible via the custom domain
- Log in as the admin user and verify write operations work
- Log in as a viewer user and verify write operations are blocked
- Confirm Grafana dashboards were automatically imported

### Backward Compatibility

- Without a custom domain configured, the console remains accessible via ALB DNS
- Without RBAC groups assigned, all users retain full admin permissions (same as Phase 2A)
- Use `--skip-dashboard-import` to skip dashboard provisioning

---

## Custom Domain Setup

### How It Works

A conditional Route 53 Alias record is added to the CloudFormation template (`console.yaml`):

```
User → console.example.com (Route 53 Alias)
     → ALB (HTTPS/443, ACM certificate)
     → Cognito authentication
     → ToolJet UI
```

- When `CustomDomainName` is empty, no Route 53 resource is created
- Direct ALB DNS access continues to work regardless
- The custom domain is automatically added to Cognito callback URLs

### Setup Steps

#### 1. Prepare the ACM Certificate

Issue an ACM certificate in the same region as the ALB and complete DNS validation:

```bash
# Verify certificate status
aws acm describe-certificate \
  --certificate-arn "arn:aws:acm:ap-northeast-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --query 'Certificate.Status'
# Should return "ISSUED"
```

#### 2. Set Environment Variables

```bash
export CUSTOM_DOMAIN_NAME="console.example.com"
export HOSTED_ZONE_ID="Z0123456789ABCDEFGHIJ"
export CERTIFICATE_ARN="arn:aws:acm:ap-northeast-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

#### 3. Deploy

```bash
cd management-console/scripts
bash deploy.sh
```

After deployment completes, the console URL is displayed:

```
✅ Console URL: https://console.example.com
```

#### 4. Verify DNS Propagation

```bash
# Check DNS resolution (propagation may take a few minutes)
dig console.example.com +short
# Should return the ALB DNS name
```

### Removing the Custom Domain

To remove the custom domain, unset the variables and redeploy:

```bash
unset CUSTOM_DOMAIN_NAME
unset HOSTED_ZONE_ID
bash deploy.sh
```

The cleanup script (`cleanup.sh`) automatically deletes the Route 53 record during teardown.

---

## RBAC Configuration

### How It Works

RBAC combines Cognito User Pool groups with ALB OIDC authentication to enforce access control at the application level:

```
User → Cognito auth → ALB (x-amzn-oidc-data header)
     → ToolJet workflow → JWT decode → check cognito:groups claim
     → fsxn-admins group: all operations allowed
     → fsxn-viewers group: read-only operations
```

### Roles and Permissions

| Role | Cognito Group | Permissions |
|------|---------------|-------------|
| Admin | `fsxn-admins` | All operations (read + write) |
| Viewer | `fsxn-viewers` | Read-only operations |
| Unassigned | None | All operations (backward compatibility) |

> ⚠️ **Important**: If Cognito groups exist but a user is not assigned to any group, they retain full access. This preserves backward compatibility with Phase 2A.

### Write Operations Restricted to Admins

The following operations require `fsxn-admins` group membership:

| Workflow | Restricted Operation |
|----------|---------------------|
| snapshot-restore | Restore from snapshot |
| flexclone-management | Create FlexClone |
| volume-management | Resize or delete volumes |
| arp-dashboard | Create protective snapshot |

Viewers attempting these operations see an "Insufficient permissions — Admin role required" error.

### User Management

#### Creating the Initial Admin User (During Deployment)

Set the `ADMIN_EMAIL` environment variable before deploying:

```bash
export ADMIN_EMAIL="admin@example.com"
bash deploy.sh
```

- A temporary password is sent via email
- The user is prompted to change their password on first login
- The user is automatically added to the `fsxn-admins` group

#### Creating Additional Users

```bash
# Create a user
aws cognito-idp admin-create-user \
  --user-pool-id <user-pool-id> \
  --username viewer@example.com \
  --user-attributes Name=email,Value=viewer@example.com Name=email_verified,Value=true \
  --desired-delivery-mediums EMAIL

# Add to the viewers group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <user-pool-id> \
  --username viewer@example.com \
  --group-name fsxn-viewers
```

#### Changing a User's Role

```bash
# Promote from viewer to admin
aws cognito-idp admin-remove-user-from-group \
  --user-pool-id <user-pool-id> \
  --username user@example.com \
  --group-name fsxn-viewers

aws cognito-idp admin-add-user-to-group \
  --user-pool-id <user-pool-id> \
  --username user@example.com \
  --group-name fsxn-admins
```

### Technical Details

1. User authenticates via Cognito Hosted UI
2. ALB validates the OIDC token and forwards the `x-amzn-oidc-data` header (JWT) to ToolJet
3. ToolJet workflows decode the JWT and extract the `cognito:groups` claim
4. Before write operations, the workflow checks for `fsxn-admins` membership
5. If the user is not an admin, the operation is blocked with an error message

---

## Dashboard Auto-Provisioning

### How It Works

A CloudFormation Custom Resource triggers a Lambda function during stack deployment to automatically import Grafana dashboards into AMG:

```
deploy.sh
  → Upload dashboard JSONs to S3 bucket
  → Deploy observability.yaml (includes Custom Resource)
    → Custom Resource invokes Lambda
      → Lambda reads dashboard JSONs from S3
      → Lambda calls AMG API: configure AMP data source
      → Lambda calls AMG API: import each dashboard
      → Lambda returns panel embed URLs as Custom Resource output
```

### Key Features

- **Idempotent**: Dashboards are imported by UID — re-deployment safely overwrites existing dashboards
- **Rate limit handling**: Exponential backoff on AMG API 429 responses (up to 3 retries)
- **Skippable**: Use `--skip-dashboard-import` to bypass provisioning
- **On delete**: Dashboards remain in AMG for manual cleanup (no-op on stack deletion)

### Preparing the AMG API Key

Dashboard import requires an AMG API key with Admin role:

1. Open your AMG workspace in the console
2. Navigate to **Configuration** → **API keys** → **Add API key**
3. Set Role to **Admin**, Expiration as desired (recommended: 30 days)
4. Store the generated key in Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name fsxn-mgmt-grafana-api-key \
  --description "AMG API key for dashboard auto-provisioning" \
  --secret-string '{"api_key": "<your-amg-api-key>"}'
```

### Skipping Dashboard Import

If the AMG API key is not configured or you prefer to manage dashboards manually:

```bash
bash deploy.sh --skip-dashboard-import
```

This passes `SkipDashboardImport=true` to Stack 3, preventing the Custom Resource Lambda from executing.

### Dashboards Imported

All JSON files in the `harvest/dashboards/` directory are imported:

| Dashboard | File | Content |
|-----------|------|---------|
| ARP Status | `arp-status.json` | ARP state distribution, alert timeline |
| Volume Overview | `volume-overview.json` | Volume metrics overview |
| Performance | `performance.json` | IOPS, throughput, latency |

---

## Troubleshooting

### Custom Domain Issues

#### DNS Does Not Resolve

**Symptom**: `dig console.example.com` returns NXDOMAIN

**Cause**: Route 53 record was not created, or DNS propagation is still in progress

**Resolution**:
```bash
# Check if the record was created in the CloudFormation stack
aws cloudformation describe-stack-resources \
  --stack-name fsxn-mgmt-console \
  --query "StackResources[?ResourceType=='AWS::Route53::RecordSet']"

# Check the record directly in Route 53
aws route53 list-resource-record-sets \
  --hosted-zone-id Z0123456789ABCDEFGHIJ \
  --query "ResourceRecordSets[?Name=='console.example.com.']"
```

- DNS propagation can take up to a few minutes
- Verify `CUSTOM_DOMAIN_NAME` and `HOSTED_ZONE_ID` are set correctly

#### Certificate Error (HTTPS)

**Symptom**: Browser displays a certificate error

**Cause**: ACM certificate domain does not match `CUSTOM_DOMAIN_NAME`, or certificate is not in ISSUED state

**Resolution**:
```bash
# Check certificate status and domain
aws acm describe-certificate \
  --certificate-arn "<certificate-arn>" \
  --query 'Certificate.{Status:Status,DomainName:DomainName,SANs:SubjectAlternativeNames}'
```

- Ensure the certificate domain matches `CUSTOM_DOMAIN_NAME` exactly (or covers it via wildcard)
- Ensure the certificate Status is `ISSUED`

#### Validation Error During Deployment

**Symptom**: Deploy script exits with:
```
❌ CUSTOM_DOMAIN_NAME is set but CERTIFICATE_ARN or HOSTED_ZONE_ID is missing
```

**Cause**: Not all three custom domain environment variables are set

**Resolution**: Set all three: `CUSTOM_DOMAIN_NAME`, `CERTIFICATE_ARN`, and `HOSTED_ZONE_ID`

---

### RBAC Issues

#### Write Operations Blocked with "Insufficient permissions"

**Symptom**: An admin user cannot perform write operations

**Cause**: The user is not a member of the `fsxn-admins` group

**Resolution**:
```bash
# Check the user's group membership
aws cognito-idp admin-list-groups-for-user \
  --user-pool-id <user-pool-id> \
  --username <username>

# Add to fsxn-admins group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <user-pool-id> \
  --username <username> \
  --group-name fsxn-admins
```

> After changing group membership, the user must log out and log back in to refresh the OIDC token.

#### All Users Have Admin Permissions

**Symptom**: Viewer-group users can still perform write operations

**Cause**: RBAC checks are not properly applied in ToolJet workflows

**Resolution**:
- Verify `tooljet-workflows/rbac-helper.json` is correctly imported
- Verify each write workflow (snapshot-restore, flexclone-management, volume-management, arp-dashboard) includes the RBAC check
- Re-import the ToolJet workflows

#### Initial Admin User Does Not Receive Email

**Symptom**: Deployed with `ADMIN_EMAIL` set but no temporary password email arrived

**Cause**: Cognito SES configuration issue or email address typo

**Resolution**:
```bash
# Check if the user was created
aws cognito-idp admin-get-user \
  --user-pool-id <user-pool-id> \
  --username <admin-email>

# If the user exists, reset the password manually
aws cognito-idp admin-set-user-password \
  --user-pool-id <user-pool-id> \
  --username <admin-email> \
  --password "<temporary-password>" \
  --permanent
```

---

### Dashboard Auto-Provisioning Issues

#### Dashboards Not Imported

**Symptom**: After deployment, dashboards do not appear in AMG

**Cause**: AMG API key is not configured, or the Lambda encountered an error

**Resolution**:
```bash
# Check the Custom Resource Lambda logs
aws logs tail /aws/lambda/fsxn-mgmt-dashboard-importer --since 30m

# Verify the API key exists in Secrets Manager
aws secretsmanager describe-secret \
  --secret-id fsxn-mgmt-grafana-api-key
```

- If the API key has expired, regenerate it and update Secrets Manager
- Verify `--skip-dashboard-import` was not passed to the deploy script

#### AMG API Rate Limit Errors

**Symptom**: Lambda logs show `429 Too Many Requests`

**Cause**: AMG API rate limit reached (too many dashboards imported in a short window)

**Resolution**:
- The Lambda automatically retries with exponential backoff (up to 3 attempts)
- If retries are exhausted, wait a few minutes and redeploy
- For large numbers of dashboards, consider splitting across multiple deployments

#### Dashboard JSONs Not Uploaded to S3

**Symptom**: Lambda logs show "No dashboard files found in S3"

**Cause**: The deploy script failed to upload files to S3

**Resolution**:
```bash
# Check S3 bucket contents
aws s3 ls s3://fsxn-mgmt-dashboards-123456789012/

# Upload manually
aws s3 sync harvest/dashboards/ s3://fsxn-mgmt-dashboards-123456789012/dashboards/
```

---

### General Issues

#### Phase 2A Features Stopped Working

**Symptom**: Existing workflows fail after the Phase 2B upgrade

**Cause**: Unlikely under normal circumstances; may indicate a parameter misconfiguration

**Resolution**:
- Phase 2B changes are additive and do not modify existing functionality
- Verify ECS tasks are running:
  ```bash
  aws ecs describe-services \
    --cluster fsxn-mgmt-cluster \
    --services fsxn-mgmt-tooljet \
    --query 'services[0].{desired:desiredCount,running:runningCount}'
  ```
- If the issue persists, unset all Phase 2B environment variables and redeploy

---

## Reference

### Deploy Script Parameters (Phase 2B Additions)

```bash
# Custom domain (optional — all three must be set together)
export CUSTOM_DOMAIN_NAME="console.example.com"
export HOSTED_ZONE_ID="Z0123456789ABCDEFGHIJ"
export CERTIFICATE_ARN="arn:aws:acm:ap-northeast-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# RBAC initial admin (optional)
export ADMIN_EMAIL="admin@example.com"

# Skip dashboard import (optional)
bash deploy.sh --skip-dashboard-import
```

### CloudFormation Parameters (Phase 2B Additions)

| Parameter | Template | Type | Default | Description |
|-----------|----------|------|---------|-------------|
| `CustomDomainName` | console.yaml | String | '' | Custom domain name |
| `HostedZoneId` | console.yaml | String | '' | Route 53 hosted zone ID |
| `SkipDashboardImport` | observability.yaml | String | 'false' | Skip dashboard import |

### Cognito Groups

| Group Name | Precedence | Description |
|------------|-----------|-------------|
| `fsxn-admins` | 1 | Administrators (full access) |
| `fsxn-viewers` | 10 | Viewers (read-only) |
