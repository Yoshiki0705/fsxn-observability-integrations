# ONTAP Audit Setup Guide

This guide covers the complete setup of ONTAP file access auditing on Amazon FSx for NetApp ONTAP, including audit volume creation, audit configuration, log rotation, and verification.

> **Reference**: [AWS Documentation — File access auditing](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)

## Prerequisites

- FSx for ONTAP file system with at least one SVM
- ONTAP CLI access via `fsxadmin` credentials
- Sufficient storage capacity for audit logs

## Audit Volume Creation

Create a dedicated volume to store audit log files. A separate volume is recommended to isolate audit data from production workloads and simplify capacity management.

```bash
# Create audit volume on the SVM's aggregate
vol create -vserver svm-prod-01 -volume audit_logs -aggregate aggr1 \
  -size 50GB -state online -type RW -security-style ntfs \
  -snapshot-policy none -tiering-policy none
```

### Junction Path Configuration

Mount the audit volume at a junction path accessible to the SVM:

```bash
# Create junction path for the audit volume
vol mount -vserver svm-prod-01 -volume audit_logs -junction-path /audit
```

> **Note**: The junction path must exist before enabling auditing. ONTAP writes audit logs to this path.

## Audit Configuration

### Creating the Audit Configuration

Use `vserver audit create` to define the audit policy for the SVM:

```bash
# Create audit configuration with EVTX format and time-based rotation
vserver audit create -vserver svm-prod-01 \
  -events file-ops \
  -format evtx \
  -destination /audit \
  -rotate-schedule-month - \
  -rotate-schedule-dayofweek - \
  -rotate-schedule-day - \
  -rotate-schedule-hour 0,6,12,18 \
  -rotate-schedule-minute 0
```

### Enabling and Managing Auditing

```bash
# Enable auditing on the SVM
vserver audit enable -vserver svm-prod-01

# Verify audit configuration
vserver audit show -vserver svm-prod-01 -instance

# Disable auditing (if needed)
vserver audit disable -vserver svm-prod-01
```

## EVTX vs XML Format Selection

Choose the log format based on your environment and integration requirements:

| Criteria | EVTX | XML |
|----------|------|-----|
| Protocol support | SMB + NFS | SMB + NFS |
| File size | Smaller (binary) | Larger (text) |
| Parsing complexity | Requires EVTX parser | Standard XML parser |
| Windows Event Viewer | Compatible | Not compatible |
| Programmatic processing | Needs specialized library | Any XML library |
| FSx S3 Access Point retrieval | Supported | Supported |
| Recommended for | Windows-centric environments | Programmatic log pipelines |

### Selection Guidelines

- **Choose EVTX** when: Windows Event Viewer compatibility is needed, storage efficiency is a priority, or existing tooling supports EVTX parsing.
- **Choose XML** when: Simpler programmatic parsing is preferred, integration with text-based log pipelines, or when avoiding binary format dependencies.

> **Note for this project**: The `shared/lambda-layers/log-parser/` supports both EVTX and XML formats. Choose based on your operational preferences.

## Log Rotation Design

### Time-Based Rotation

Time-based rotation creates new log files at scheduled intervals regardless of file size:

```bash
# Rotate every 6 hours
vserver audit create -vserver svm-prod-01 \
  -events file-ops \
  -format evtx \
  -destination /audit \
  -rotate-schedule-month - \
  -rotate-schedule-dayofweek - \
  -rotate-schedule-day - \
  -rotate-schedule-hour 0,6,12,18 \
  -rotate-schedule-minute 0
```

### Size-Based Rotation

Size-based rotation creates new log files when the active log reaches a specified size:

```bash
# Rotate when log file reaches 100MB
vserver audit create -vserver svm-prod-01 \
  -events file-ops \
  -format evtx \
  -destination /audit \
  -rotate-size 100MB
```

### Rotation Strategy Comparison

| Strategy | Use Case | Pros | Cons |
|----------|----------|------|------|
| Time-based | Predictable processing schedules | Consistent file creation timing | File sizes vary |
| Size-based | High-volume environments | Consistent file sizes | Unpredictable timing |
| Combined | Production environments | Balanced approach | More complex configuration |

### Recommended Configuration

For integration with EventBridge Scheduler-based log processing (this project's pattern):

- **Time-based rotation every 1–6 hours** aligns well with scheduled Lambda invocations
- Ensures rotated files are available for processing at predictable intervals
- Avoid rotation intervals shorter than the Lambda schedule interval

## Audit Volume Sizing Guidelines

Estimate audit volume size based on your environment's file operation volume:

| Environment | Daily File Ops | Estimated Daily Log Size | Recommended Volume |
|-------------|---------------|--------------------------|-------------------|
| Small (< 50 users) | ~10,000 | ~50 MB | 10 GB |
| Medium (50–500 users) | ~100,000 | ~500 MB | 50 GB |
| Large (500+ users) | ~1,000,000+ | ~5 GB+ | 200 GB+ |

### Sizing Considerations

- EVTX format is approximately 30–50% smaller than XML for the same events
- Retain at least 7 days of rotated logs before cleanup
- Account for burst activity (month-end processing, migrations)
- Monitor volume utilization with ONTAP `vol show -fields used`

```bash
# Check audit volume usage
vol show -vserver svm-prod-01 -volume audit_logs -fields size,used,available
```

## SACL Configuration for SMB

System Access Control Lists (SACLs) define which file operations generate audit events for SMB access. SACLs are configured on individual files or directories using Windows security tools.

### Configuring SACLs

```powershell
# PowerShell: Set audit SACL on a shared folder
$acl = Get-Acl "\\fsxn-server\share\sensitive-data"
$auditRule = New-Object System.Security.AccessControl.FileSystemAuditRule(
    "Everyone",
    "Read,Write,Delete",
    "ContainerInherit,ObjectInherit",
    "None",
    "Success,Failure"
)
$acl.AddAuditRule($auditRule)
Set-Acl "\\fsxn-server\share\sensitive-data" $acl
```

### SACL Best Practices

| Recommendation | Rationale |
|---------------|-----------|
| Audit specific folders, not entire volumes | Reduces log volume and noise |
| Focus on `Write` and `Delete` operations | Most relevant for security monitoring |
| Include both `Success` and `Failure` | Failure events indicate unauthorized access attempts |
| Use group-based rules | Easier to manage than per-user rules |

## NFSv4 ACL Audit Flags for NFS

For NFS file access auditing, ONTAP uses NFSv4 ACL audit flags (also called SACL-equivalent flags) to determine which operations to audit.

### Setting NFSv4 Audit Flags

```bash
# Set audit flags on a directory using nfs4_setfacl
nfs4_setfacl -a "A:fdS:EVERYONE@:rwaxtTnNcCoy" /mnt/fsxn/audit-target/

# Verify audit flags
nfs4_getfacl /mnt/fsxn/audit-target/
```

### NFSv4 Audit Flag Reference

| Flag | Meaning | Audited Operation |
|------|---------|-------------------|
| `S` | Successful access | Audit successful operations |
| `F` | Failed access | Audit failed operations |
| `r` | Read data | File read operations |
| `w` | Write data | File write operations |
| `a` | Append data | File append operations |
| `x` | Execute | File execution |
| `d` | Delete | File/directory deletion |
| `D` | Delete child | Delete items within directory |

## Active Log File vs Rotated Log File Behavior

Understanding the difference between active and rotated log files is critical for log processing pipelines.

### Active Log File

- File name: `audit.evtx` or `audit.xml` (no timestamp suffix)
- Actively being written to by ONTAP
- **Do NOT process active log files** — they may be incomplete or locked
- Located at: `/audit/audit.evtx`

### Rotated Log File

- File name includes timestamp: `audit_<timestamp>.evtx`
- Complete and closed — safe for processing
- Created when rotation triggers (time or size threshold)
- Located at: `/audit/audit_20260115120000.evtx`

```bash
# List rotated audit log files
vol file show -vserver svm-prod-01 -volume audit_logs -path /audit/audit_*.evtx
```

### Processing Implications

| Aspect | Active Log | Rotated Log |
|--------|-----------|-------------|
| Status | Being written | Closed/complete |
| Safe to read | No | Yes |
| File name pattern | `audit.evtx` | `audit_<timestamp>.evtx` |
| Lambda processing | Skip | Process |
| S3 AP visibility | Visible but incomplete | Visible and complete |

> **Design rule**: The Lambda log processor in this project only reads rotated files (files matching `audit_*.evtx` or `audit_*.xml` pattern). The active log file is always skipped.

## Audit Volume Full Behavior

When the audit volume reaches capacity, ONTAP behavior depends on the `rotate-limit` and volume configuration:

### Default Behavior

1. ONTAP attempts to rotate the active log file
2. If rotation fails due to space, the **oldest rotated log files are deleted** to make room
3. If no rotated files can be deleted, **auditing stops** and events are lost

### Mitigation Strategies

```bash
# Set rotation limit to control maximum number of rotated files
vserver audit modify -vserver svm-prod-01 -rotate-limit 100

# Enable volume autogrow
vol autosize -vserver svm-prod-01 -volume audit_logs \
  -mode grow -maximum-size 200GB -grow-threshold-percent 85
```

| Strategy | Configuration | Trade-off |
|----------|--------------|-----------|
| Rotation limit | `-rotate-limit 100` | Oldest logs auto-deleted |
| Volume autogrow | `vol autosize -mode grow` | Uses more storage |
| External cleanup | Lambda-based cleanup | Requires additional automation |
| Monitoring alerts | CloudWatch on volume usage | Reactive, not preventive |

> **Recommendation**: Combine volume autogrow with a rotation limit. Monitor volume usage and alert at 80% capacity.

## Verification

### Confirm Rotated Files Exist

After enabling auditing and waiting for the first rotation interval, verify that rotated log files are being created:

```bash
# SSH to FSx for ONTAP CLI and list audit files
vserver audit show -vserver svm-prod-01 -instance

# List files in the audit volume
vol file show -vserver svm-prod-01 -volume audit_logs -path /

# Check for rotated files (should see timestamped files)
vol file show -vserver svm-prod-01 -volume audit_logs -path /audit_*.evtx
```

Expected output should show files like:
- `audit.evtx` (active log)
- `audit_20260115000000.evtx` (rotated)
- `audit_20260115060000.evtx` (rotated)

### Confirm Files Visible Through FSx S3 Access Point

Verify that audit log files are accessible via the FSx for ONTAP S3 Access Point:

```bash
# List objects via S3 Access Point
aws s3api list-objects-v2 \
  --bucket arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --prefix "svm-prod-01/audit/" \
  --region ap-northeast-1

# Download a rotated file to verify content
aws s3api get-object \
  --bucket arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --key "svm-prod-01/audit/audit_20260115000000.evtx" \
  --region ap-northeast-1 \
  /tmp/test-audit.evtx

# Verify file is valid EVTX (check magic bytes)
xxd /tmp/test-audit.evtx | head -1
# Expected: 456c 6646 696c 6500 (ElfFile\0)
```

> **Troubleshooting**: If files are not visible through the S3 Access Point, verify:
> 1. The S3 Access Point is configured for the correct SVM
> 2. The junction path matches the audit destination
> 3. IAM permissions include `s3:GetObject` on the Access Point ARN
> 4. Network connectivity (Lambda outside VPC, or NAT Gateway if inside VPC)

## Summary

| Step | Command / Action | Verification |
|------|-----------------|--------------|
| 1. Create volume | `vol create` | `vol show` |
| 2. Mount volume | `vol mount` | `vol show -junction-path` |
| 3. Create audit config | `vserver audit create` | `vserver audit show` |
| 4. Enable auditing | `vserver audit enable` | `vserver audit show -state` |
| 5. Configure SACLs/ACLs | Windows SACL or NFSv4 flags | Test file access |
| 6. Verify rotation | Wait for interval | `vol file show` |
| 7. Verify S3 AP access | `aws s3api list-objects-v2` | Files listed |
