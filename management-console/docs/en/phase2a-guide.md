# FSxN Management Console — Phase 2A Guide

This guide covers the Phase 2A features added to the FSxN Management Console: ARP (Anti-Ransomware Protection) dashboard, snapshot restore workflow, FlexClone management, and multi-poller support for monitoring multiple FSx for ONTAP file systems.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Upgrading from Phase 1](#upgrading-from-phase-1)
4. [Multi-Poller Configuration](#multi-poller-configuration)
5. [ARP Dashboard](#arp-dashboard)
6. [Snapshot Restore Workflow](#snapshot-restore-workflow)
7. [FlexClone Management](#flexclone-management)
8. [File System Selector](#file-system-selector)
9. [Grafana ARP Dashboard](#grafana-arp-dashboard)
10. [Troubleshooting](#troubleshooting)

---

## Overview

Phase 2A extends the existing Phase 1 Management Console with four key capabilities:

| Feature | Description | ONTAP Version |
|---------|-------------|---------------|
| ARP Dashboard | Ransomware protection status visibility with alerts and one-click protective snapshots | 9.17+ |
| Snapshot Restore | Full restore-from-snapshot workflow with confirmation and progress tracking | 9.8+ |
| FlexClone Management | Create writable clones from volumes/snapshots with parent relationship visibility | 9.8+ |
| Multi-Poller Support | Monitor up to 10 FSx for ONTAP file systems from a single deployment | 9.8+ |

All Phase 2A features are delivered as updates to existing CloudFormation stacks and new ToolJet workflow files. Existing Phase 1 functionality (volume management, SVM management, snapshot CRUD, replication management, S3 file browser) is fully preserved.

---

## Prerequisites

### Existing Phase 1 Deployment

Phase 2A is an upgrade to an existing Phase 1 deployment. Ensure the following stacks are deployed and healthy:

```
fsxn-mgmt-network
fsxn-mgmt-auth
fsxn-mgmt-observability
fsxn-mgmt-console
fsxn-mgmt-monitoring
```

### ONTAP Version Requirements

| Feature | Minimum ONTAP Version | Notes |
|---------|----------------------|-------|
| ARP/AI Dashboard | **9.17+** | ARP/AI features are not available on earlier versions |
| Snapshot Restore | 9.8+ | Standard ONTAP REST API |
| FlexClone | 9.8+ | Standard ONTAP REST API |
| Multi-Poller | 9.8+ | No version dependency (Harvest-side configuration) |

> **Note**: If your FSx for ONTAP file system runs a version earlier than 9.17, the ARP dashboard will display a notification indicating that ARP/AI features require ONTAP 9.17 or later. All other Phase 2A features will function normally.

### Multi-Poller Prerequisites (if monitoring multiple file systems)

For each additional FSx for ONTAP file system, prepare:

1. **Management endpoint** — IP address or DNS name (port 443 accessible from private subnets)
2. **Secrets Manager secret** — ONTAP admin credentials in JSON format:

```json
{
  "username": "fsxadmin",
  "password": "<password>"
}
```

Create a secret for each file system:

```bash
# File system 1 (may already exist from Phase 1)
aws secretsmanager create-secret \
  --name fsxn-mgmt-ontap-credentials-fs1 \
  --secret-string '{"username":"fsxadmin","password":"<password-1>"}'

# File system 2
aws secretsmanager create-secret \
  --name fsxn-mgmt-ontap-credentials-fs2 \
  --secret-string '{"username":"fsxadmin","password":"<password-2>"}'

# File system 3
aws secretsmanager create-secret \
  --name fsxn-mgmt-ontap-credentials-fs3 \
  --secret-string '{"username":"fsxadmin","password":"<password-3>"}'
```

---

## Upgrading from Phase 1

Phase 2A is fully backward compatible with Phase 1. The upgrade process updates existing stacks with new parameters.

### Parameter Changes

| Phase 1 Parameter (singular) | Phase 2A Parameter (plural) | Notes |
|------------------------------|----------------------------|-------|
| `OntapManagementEndpoint` | `OntapManagementEndpoints` | Comma-separated (1–10 endpoints) |
| `OntapCredentialsSecretArn` | `OntapCredentialsSecretArns` | Comma-separated (positional match) |

> **Backward compatibility**: The deploy script automatically converts the legacy singular environment variables (`ONTAP_MGMT_ENDPOINT`, `ONTAP_CREDENTIALS_SECRET_ARN`) to the plural form. Existing single-endpoint deployments work without changes.

### Upgrade Steps

#### 1. Update environment variables

For a single file system (no changes needed):

```bash
# Legacy variables still work
export ONTAP_MGMT_ENDPOINT="<management-ip>"
export ONTAP_CREDENTIALS_SECRET_ARN="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX"
```

For multiple file systems:

```bash
export ONTAP_MGMT_ENDPOINTS="<management-ip-1>,<management-ip-2>,<management-ip-3>"
export ONTAP_CREDENTIALS_SECRET_ARNS="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-fs1-XXXXXX,arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-fs2-XXXXXX,arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-fs3-XXXXXX"
```

#### 2. Run the deploy script

```bash
cd management-console
bash scripts/deploy.sh
```

The script validates that:
- The number of endpoints matches the number of secret ARNs (positional correspondence)
- The endpoint count is between 1 and 10

#### 3. Import new ToolJet workflows

After the stack update completes, import the new workflow JSON files into ToolJet:

- `tooljet-workflows/arp-dashboard.json` — ARP status dashboard
- `tooljet-workflows/snapshot-restore.json` — Snapshot restore workflow
- `tooljet-workflows/flexclone-management.json` — FlexClone creation and listing

#### 4. Import ARP Grafana dashboard

Import the ARP dashboard into your AMG workspace:

- `harvest/dashboards/arp-status.json` — ARP state distribution and alert timeline

---

## Multi-Poller Configuration

Multi-poller support allows a single Harvest deployment to collect metrics from up to 10 FSx for ONTAP file systems simultaneously.

### How It Works

1. The deploy script passes comma-separated endpoints and secret ARNs to the ECS task definition
2. The Harvest container entrypoint (`/busybox/sh`) generates a `harvest.yml` with one poller per endpoint
3. Each poller receives a unique `datacenter` label (`fsxn-1`, `fsxn-2`, ...) for metric isolation
4. Pollers bind to sequential ports starting at 12990 (range: 12990–12999)
5. The ADOT sidecar scrapes all active ports and remote-writes to AMP

### Generated harvest.yml Structure

For a 3-endpoint deployment, the generated configuration looks like:

```yaml
Pollers:
  fsxn-cluster-1:
    datacenter: fsxn-1
    addr: <management-ip-1>
    auth_style: basic_auth
    username: fsxadmin
    password: <from-secret-1>
    collectors:
      - Rest
      - RestPerf
    exporters:
      - prometheus
    schedule:
      - data: 60s

  fsxn-cluster-2:
    datacenter: fsxn-2
    addr: <management-ip-2>
    auth_style: basic_auth
    username: fsxadmin
    password: <from-secret-2>
    collectors:
      - Rest
      - RestPerf
    exporters:
      - prometheus
    schedule:
      - data: 60s

  fsxn-cluster-3:
    datacenter: fsxn-3
    addr: <management-ip-3>
    auth_style: basic_auth
    username: fsxadmin
    password: <from-secret-3>
    collectors:
      - Rest
      - RestPerf
    exporters:
      - prometheus
    schedule:
      - data: 60s

Exporters:
  prometheus:
    exporter: Prometheus
    port_range: 12990-12999

Defaults:
  use_insecure_tls: true
```

### Poller Isolation

Each poller operates independently. If one poller fails to connect to its target endpoint, all other pollers continue collecting metrics without interruption. A CloudWatch alarm identifies the failed poller by name.

### IAM Permissions

The updated CloudFormation templates grant `secretsmanager:GetSecretValue` on all specified secret ARNs for both the Harvest task role and the ToolJet task role:

```yaml
# IAM policy resource (generated from comma-separated ARNs)
Resource: !Split [',', !Ref OntapCredentialsSecretArns]
```

---

## ARP Dashboard

The ARP (Autonomous Ransomware Protection) dashboard provides visibility into the ransomware protection status of all volumes.

> **Requirement**: ONTAP 9.17+ is required for ARP/AI features.

### Features

- **Summary cards** — Count of volumes per ARP state (disabled, dry_run, enabled, paused)
- **Volume table** — Name, SVM, ARP state (color-coded badge), time in state, last suspicious activity
- **Filter dropdown** — Filter by ARP state with sub-2-second response
- **Search field** — Filter by volume name or SVM name (case-insensitive)
- **Alerts panel** — Active ARP alerts sorted by timestamp (descending)
- **One-click protective snapshot** — Create a snapshot for volumes with active alerts
- **Embedded Grafana panel** — ARP pie chart and timeline (auto-refresh every 60 seconds)

### ARP State Color Codes

| State | Color | Hex Code | Meaning |
|-------|-------|----------|---------|
| disabled | Red | `#DC3545` | No ransomware protection |
| dry_run | Yellow | `#FFC107` | Learning mode (not yet blocking) |
| enabled | Green | `#28A745` | Active protection |
| paused | Grey | `#6C757D` | Temporarily paused |

### Protective Snapshot

When an ARP alert is detected, you can create a protective snapshot with one click. The snapshot name follows the format:

```
arp_protect_<volume_name>_<YYYYMMDD_HHMMSS>
```

This preserves the current volume state before any potential ransomware damage spreads further.

### ONTAP REST API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/storage/volumes?fields=anti_ransomware` | GET | Fetch ARP state per volume |
| `/api/security/anti-ransomware/volumes` | GET | Fetch ARP alert events |
| `/api/storage/volumes/{uuid}/snapshots` | POST | Create protective snapshot |

---

## Snapshot Restore Workflow

The snapshot restore workflow provides a complete restore-from-snapshot operation with confirmation dialogs and progress tracking.

### Workflow Steps

1. **Select volume** — Choose the target volume from the volume list
2. **Select snapshot** — View available snapshots (sorted by creation time, newest first)
3. **Confirm restore** — Review the confirmation dialog with data loss warnings
4. **Monitor progress** — Track the restore job status (polled every 5 seconds)
5. **View result** — See success confirmation or error details

### Confirmation Dialog

The confirmation dialog displays:

- Volume name
- Snapshot name and creation timestamp
- ⚠️ Warning: "All data written after {snapshot_time} will be permanently lost"
- ⚠️ Additional warning (if volume has NAS shares): "Connected NFS/CIFS clients may experience disruption"

The restore operation does not proceed unless the user explicitly confirms.

### Job Polling

After initiating the restore, the workflow polls `GET /api/cluster/jobs/{job_uuid}` every 5 seconds until the job reaches a terminal state:

| Job State | Action |
|-----------|--------|
| `queued` | Continue polling, display "Queued" status |
| `running` | Continue polling, display "Restoring..." with progress |
| `success` | Display success confirmation with completion timestamp |
| `failure` | Display ONTAP error code and message |

### ONTAP REST API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/storage/volumes/{uuid}/snapshots` | GET | List snapshots for volume |
| `/api/storage/volumes/{uuid}/snapshots/{snap_uuid}/restore` | POST | Initiate restore |
| `/api/cluster/jobs/{job_uuid}` | GET | Poll job status |

---

## FlexClone Management

FlexClone management provides clone creation from volumes or snapshots, with validation and parent relationship visibility.

### Clone Creation

#### Input Fields

| Field | Validation Rule | Error Message |
|-------|----------------|---------------|
| Clone name | `^[a-zA-Z0-9_]{1,203}$` | "Clone name must be 1–203 characters, alphanumeric and underscores only" |
| Junction path | `^/[a-zA-Z0-9_/\-]+$` | "Junction path must start with / and contain only valid path characters" |
| Parent snapshot | Optional | Pre-populated when initiated from a snapshot |

Validation is performed client-side. Invalid input prevents the API call from being made.

#### Clone Creation API Request

```json
{
  "name": "<clone_name>",
  "clone": {
    "parent_volume": { "uuid": "<parent_volume_uuid>" },
    "parent_snapshot": { "uuid": "<parent_snapshot_uuid>" },
    "is_flexclone": true
  },
  "nas": {
    "path": "<junction_path>"
  },
  "svm": {
    "uuid": "<parent_svm_uuid>"
  }
}
```

### Clone Listing

The volume list displays additional metadata for FlexClone volumes:

- **Clone indicator badge** — Visual distinction from regular volumes
- **Parent volume name** — Source volume the clone was created from
- **Parent snapshot name** — Source snapshot (if cloned from a snapshot)
- **Clone creation time** — When the clone was created
- **Split status** — `not_split` or `split_initiated`
- **Space savings** — Shared blocks vs unique blocks

### ONTAP REST API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/storage/volumes` | POST | Create FlexClone (with `clone` body) |
| `/api/storage/volumes?fields=clone,space.logical_space,space.used` | GET | List volumes with clone metadata |
| `/api/cluster/jobs/{job_uuid}` | GET | Poll job status |

---

## File System Selector

When multiple FSx for ONTAP file systems are configured, a file system selector appears in the navigation header.

### Behavior

1. The selector displays the currently active file system name/endpoint
2. On selection change, the Management UI:
   - Updates the global `ontap_base_url` to the selected endpoint
   - Fetches credentials from the corresponding Secrets Manager ARN
   - Refreshes the current view within 3 seconds
3. A visual indicator on all pages shows which file system is active
4. If the selected endpoint is unreachable, an error is displayed for that file system — you can switch to another without a page reload

### Credential Isolation

Each file system uses only its own credentials. The positional mapping ensures:

```
Endpoint[0] → Secret ARN[0]
Endpoint[1] → Secret ARN[1]
Endpoint[2] → Secret ARN[2]
...
```

Credentials from one file system are never used for another.

---

## Grafana ARP Dashboard

A dedicated Grafana dashboard (`harvest/dashboards/arp-status.json`) provides ARP metric visualization in AMG.

### Dashboard Panels

| Panel | Type | PromQL |
|-------|------|--------|
| ARP State Distribution | Pie chart | `count by (anti_ransomware_state) (ontap_volume_anti_ransomware_state)` |
| ARP Alert Timeline | Time-series | `sum(rate(ontap_volume_anti_ransomware_attack_detected_total[5m])) by (volume)` |
| Per-Volume ARP Event Count | Table | `sum by (volume, svm) (ontap_volume_anti_ransomware_attack_detected_total)` |

### Dashboard Variables

- `$datacenter` — Cluster/datacenter selector (maps to Harvest `datacenter` label)
- All panels filter by the selected datacenter variable

### Importing the Dashboard

```bash
# The dashboard JSON is located at:
management-console/harvest/dashboards/arp-status.json

# Import via AMG UI: Dashboards → Import → Upload JSON file
```

> **Note**: ARP metrics availability depends on Harvest version and ONTAP 9.17+ REST API support. If Harvest does not export ARP-specific Prometheus metrics, the ToolJet-embedded approach (direct REST API polling) serves as the primary data source.

---

## Troubleshooting

### Multi-Poller Issues

#### Endpoint/Secret Count Mismatch

**Symptom**: Deploy script exits with "Endpoint count does not match secret ARN count"

**Cause**: The number of comma-separated endpoints does not equal the number of comma-separated secret ARNs.

**Resolution**: Verify that each endpoint has a corresponding secret ARN in the same position:

```bash
# Check counts
echo "${ONTAP_MGMT_ENDPOINTS}" | tr ',' '\n' | wc -l
echo "${ONTAP_CREDENTIALS_SECRET_ARNS}" | tr ',' '\n' | wc -l
```

#### Single Poller Connection Failure

**Symptom**: Metrics missing for one file system, others are fine.

**Cause**: One poller cannot reach its target endpoint (network or credential issue).

**Resolution**:
1. Check CloudWatch alarms for the specific poller name
2. Verify the endpoint is reachable from private subnets on port 443
3. Verify the corresponding secret contains valid credentials:

```bash
aws secretsmanager get-secret-value \
  --secret-id <secret-arn> \
  --query "SecretString" --output text | jq .
```

#### All Pollers Fail

**Symptom**: No metrics from any file system after deployment.

**Cause**: ECS health check failure triggers deployment circuit breaker rollback.

**Resolution**:
1. Check ECS task stopped reason
2. Verify Harvest container logs:

```bash
aws logs tail /ecs/fsxn-mgmt-harvest --since 30m
```

### ARP Dashboard Issues

#### "ARP/AI features require ONTAP 9.17 or later"

**Symptom**: ARP dashboard shows version requirement notification.

**Cause**: The connected FSx for ONTAP file system runs an ONTAP version earlier than 9.17.

**Resolution**: Upgrade the FSx for ONTAP file system to ONTAP 9.17 or later. ARP/AI features are not available on earlier versions.

#### "Data source unavailable"

**Symptom**: ARP dashboard shows data source error banner.

**Cause**: The ONTAP REST API is unreachable from the ToolJet container.

**Resolution**:
1. Verify the management endpoint is accessible from private subnets
2. Check security group rules allow outbound port 443
3. Verify credentials in Secrets Manager are valid

### Snapshot Restore Issues

#### Restore Job Fails

**Symptom**: Job polling shows `failure` state with ONTAP error.

**Common causes**:
- Volume is in a SnapMirror relationship (break mirror first)
- Insufficient space in the aggregate
- Volume is offline

**Resolution**: Review the ONTAP error code and message displayed in the UI. Address the underlying issue and retry.

### FlexClone Issues

#### Clone Creation Fails with Error 917927

**Symptom**: ONTAP returns error code 917927 during clone creation.

**Cause**: Insufficient space in the aggregate for the clone metadata.

**Resolution**: Free space in the aggregate or move the parent volume to an aggregate with available capacity.

#### Validation Error on Clone Name

**Symptom**: Field-level error "Clone name must be 1–203 characters, alphanumeric and underscores only"

**Cause**: Clone name contains invalid characters (spaces, hyphens, special characters) or exceeds 203 characters.

**Resolution**: Use only letters (a-z, A-Z), numbers (0-9), and underscores (_). Maximum length is 203 characters.

### File System Selector Issues

#### Connection Error After Switching

**Symptom**: "Connection error" displayed after selecting a different file system.

**Cause**: The selected endpoint is unreachable or credentials are invalid.

**Resolution**:
1. Verify the endpoint is accessible from the ToolJet container's subnet
2. Verify the corresponding Secrets Manager secret contains valid credentials
3. Switch to a different file system while investigating

---

## Reference

### New Files Added in Phase 2A

```
management-console/
├── tooljet-workflows/
│   ├── arp-dashboard.json          # ARP status dashboard
│   ├── snapshot-restore.json       # Snapshot restore workflow
│   └── flexclone-management.json   # FlexClone creation and listing
├── harvest/
│   └── dashboards/
│       └── arp-status.json         # ARP Grafana dashboard
└── docs/
    ├── ja/
    │   └── phase2a-guide.md        # This guide (Japanese)
    └── en/
        └── phase2a-guide.md        # This guide (English)
```

### Modified Files in Phase 2A

| File | Changes |
|------|---------|
| `templates/observability.yaml` | Multi-poller parameters, entrypoint update, ADOT scrape config |
| `templates/console.yaml` | Multi-secret IAM, endpoint list environment variables |
| `scripts/deploy.sh` | Multi-endpoint validation, backward-compatible parameter handling |
| `tooljet-workflows/volume-management.json` | FlexClone listing enhancement (clone badge, parent info) |

### Deploy Script Parameters

```bash
# Required
export VPC_ID="vpc-0123456789abcdef0"
export PRIVATE_SUBNET_IDS="subnet-aaaa,subnet-bbbb"
export PUBLIC_SUBNET_IDS="subnet-cccc,subnet-dddd"
export ONTAP_MGMT_ENDPOINTS="<management-ip-1>,<management-ip-2>"
export ONTAP_CREDENTIALS_SECRET_ARNS="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fs1-XXXXXX,arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fs2-XXXXXX"

# Optional
export CERTIFICATE_ARN="arn:aws:acm:ap-northeast-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export S3_ACCESS_POINT_ARN="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-file-ap"
export HARVEST_IMAGE_TAG="24.05.2"
export TOOLJET_IMAGE_TAG="latest"
export MFA_CONFIGURATION="OPTIONAL"
export SESSION_DURATION_HOURS="8"
export FSXN_SECURITY_GROUP_ID="sg-0123456789abcdef0"
```
