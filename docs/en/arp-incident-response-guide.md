# ARP (Autonomous Ransomware Protection) Incident Response Guide

🌐 [日本語](../ja/arp-incident-response-guide.md) | **English** (this page)

## Overview

This guide defines the incident response procedures when ONTAP's Autonomous Ransomware Protection (ARP) detects a suspected ransomware attack. It covers the action flow after an alert arrives at your Observability platform (Datadog, etc.) via EMS Webhook.

## How ARP Detection Works

ARP uses AI/ML to detect the following anomalies:

| Detection Type | Description |
|---------------|-------------|
| Entropy changes | Abnormal increase in data randomness (encryption indicator) |
| File extension changes | Appearance of unusual extensions (20+ files) |
| IOPS anomalies | Surge in abnormal volume activity with encrypted data |

Actions on detection:
1. **Automatic ARP snapshot creation** — prefixed with `Anti_ransomware_backup`
2. **EMS event emission** — `arw.volume.state` event (severity: alert)
3. **Notification to Observability platform via this project's EMS Webhook**

---

## Incident Response Flow

```
[ARP Detection] → [EMS Webhook] → [Observability Alert]
                                          ↓
                                  [1. Initial Response]
                                          ↓
                                  [2. Scope Assessment]
                                          ↓
                                  [3. Attack Verification]
                                          ↓
                        ┌─────────────────┴─────────────────┐
                        ↓                                   ↓
                [False Positive]                    [Attack Confirmed]
                        ↓                                   ↓
                [4a. Clear Alert]                   [4b. Containment]
                                                            ↓
                                                   [5. Data Recovery]
                                                            ↓
                                                   [6. Post-Incident]
```

---

## Step 1: Initial Response (Within 5 Minutes of Detection)

### Verification in Observability Platform

Search in Datadog (or other vendor):

```
# Datadog search query
source:fsxn-ems @attributes.event_name:arw.volume.state
```

Information to verify:
- **severity**: `alert` (high probability) or `warning` (moderate probability)
- **volume_name**: Affected volume name
- **state**: `attack-detected` or `attack-suspected`
- **timestamp**: Detection time

### Immediate Actions

1. **Create incident ticket** — Record detection time, volume name, severity
2. **Notify stakeholders** — Security team, storage administrators, affected business owners
3. **Verify ARP snapshot** — Confirm the automatically created snapshot exists

```bash
# ONTAP CLI: Verify ARP snapshots
ssh admin@<management-ip> "volume snapshot show -vserver <svm-name> -volume <volume-name> -snapshot Anti_ransomware*"
```

---

## Step 2: Scope Assessment

### Investigation via ONTAP CLI

```bash
# Check ARP status
ssh admin@<management-ip> "security anti-ransomware volume show -vserver <svm-name> -volume <volume-name>"

# List suspect files
ssh admin@<management-ip> "security anti-ransomware volume show-suspect-files -vserver <svm-name> -volume <volume-name>"
```

### Additional Investigation via Observability Platform

```
# Recent file operations on the same volume (via FPolicy)
source:fsxn-fpolicy @attributes.vserver:<svm-name>

# Operations from the same client IP
source:fsxn-fpolicy @attributes.client_ip:<suspect-ip>

# Operations by the same user
source:fsxn-fpolicy @attributes.user:<suspect-user>
```

### Assessment Checklist

| Item | How to Check | Severity Indicator |
|------|-------------|-------------------|
| Affected volume count | `security anti-ransomware volume show` | Multiple volumes = severe |
| Suspect file count | `show-suspect-files` | 20+ files = high probability |
| Attack source client | FPolicy logs client_ip | Internal vs external |
| Attack source user | FPolicy logs user | Compromised legitimate user? |
| Attack time range | EMS/FPolicy log timestamps | Estimate damage scope |

---

## Step 3: Attack Verification

### Likely False Positive Cases

- Immediately after bulk file conversion (PDF→image, etc.)
- Encrypted backups by backup software
- Large build artifact generation by development teams
- During data migration activities

### Likely Real Attack Cases

- Mass appearance of unknown extensions (`.encrypted`, `.locked`, `.crypto`, etc.)
- Activity outside normal business hours
- Large-scale operations from users who don't normally access the data
- Creation of ransom notes (`README.txt`, `DECRYPT_FILES.html`, etc.)

---

## Step 4a: False Positive

```bash
# ONTAP CLI: Mark as false positive (ARP snapshot auto-deleted)
ssh admin@<management-ip> "security anti-ransomware volume attack clear-suspect -vserver <svm-name> -volume <volume-name>"
```

- ARP snapshot is automatically deleted
- Close incident ticket as "false positive"
- Adjust ARP detection parameters if needed

---

## Step 4b: Attack Confirmed — Containment

### Immediate Actions (Within 30 Minutes of Detection)

1. **Network isolation of infected client**

```bash
# Revoke infected client access via AWS Security Group
aws ec2 revoke-security-group-ingress \
  --group-id <sg-id> \
  --protocol tcp \
  --port 445 \
  --cidr <infected-client-ip>/32
```

2. **Restrict access to affected volumes**

```bash
# ONTAP CLI: Temporarily restrict CIFS share
ssh admin@<management-ip> "vserver cifs share modify -vserver <svm-name> -share-name <share-name> -access-based-enumeration false"

# Or: Restrict export policy
ssh admin@<management-ip> "export-policy rule modify -vserver <svm-name> -policyname <policy> -ruleindex <index> -clientmatch <safe-clients-only>"
```

3. **Create additional manual snapshot**

```bash
# Create point-in-time snapshot
ssh admin@<management-ip> "volume snapshot create -vserver <svm-name> -volume <volume-name> -snapshot incident_response_$(date +%Y%m%d_%H%M%S)"
```

---

## Step 5: Data Recovery

### Recovery from ARP Snapshot

```bash
# 1. List ARP snapshots
ssh admin@<management-ip> "volume snapshot show -vserver <svm-name> -volume <volume-name> -snapshot Anti_ransomware*"

# 2. Restore volume from snapshot
ssh admin@<management-ip> "volume snapshot restore -vserver <svm-name> -volume <volume-name> -snapshot Anti_ransomware_backup.<timestamp>"
```

### Individual File Recovery (via .snapshot directory)

For users recovering individual files:

```
# Windows (CIFS/SMB)
\\<server>\<share>\.snapshot\Anti_ransomware_backup.<timestamp>\<file-path>

# Linux (NFS)
/mnt/<volume>/.snapshot/Anti_ransomware_backup.<timestamp>/<file-path>
```

### Safe Recovery Verification with FlexClone

Verify before restoring the production volume:

```bash
# Create FlexClone (snapshot-based)
ssh admin@<management-ip> "volume clone create -vserver <svm-name> -flexclone <clone-name> -parent-volume <volume-name> -parent-snapshot Anti_ransomware_backup.<timestamp>"

# Mount clone for verification
ssh admin@<management-ip> "volume mount -vserver <svm-name> -volume <clone-name> -junction-path /verify_recovery"
```

---

## Step 6: Post-Incident Actions

### Required Actions

1. **Create incident report**
   - Detection time, response time, recovery completion time
   - Impact scope (volumes, files, users affected)
   - Root cause (infection vector identification)
   - Recovery method and duration

2. **Security hardening**
   - Forensic investigation of infected client
   - Password reset (compromised accounts)
   - Endpoint security updates
   - Network segmentation review

3. **ARP configuration optimization**
   - Adjust detection parameters (if false positives are frequent)
   - Expand monitored volumes
   - Review alert notification targets

4. **Backup strategy review**
   - Consider SnapLock (WORM) implementation
   - Verify AWS Backup integration
   - Re-evaluate RPO/RTO

---

## Recommended Alert Configuration

### Datadog Monitor Example

```json
{
  "name": "FSx-ONTAP ARP Ransomware Detection Alert",
  "type": "log alert",
  "query": "source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.severity:alert",
  "message": "🚨 ONTAP ARP detected suspicious activity\n\nVolume: {{@attributes.parameters.volume_name}}\nState: {{@attributes.parameters.state}}\nSeverity: {{@attributes.severity}}\n\nVerify the alert and follow the incident response guide.\nResponse guide: docs/en/arp-incident-response-guide.md",
  "options": {
    "thresholds": {"critical": 0},
    "notify_no_data": false
  }
}
```

### Recommended Alert Rules

| Alert Name | Query | Severity | Notify |
|-----------|--------|----------|--------|
| ARP Attack Detected | `source:fsxn-ems arw.volume.state severity:alert` | Critical | Security Team + Slack |
| ARP Suspect Detected | `source:fsxn-ems arw.volume.state severity:warning` | Warning | Storage Admins |
| Mass File Deletion | `source:fsxn-fpolicy operation:delete` count > 100/5min | Warning | Storage Admins |
| Abnormal Extension Change | `source:fsxn-fpolicy operation:rename` + unknown ext | Warning | Security Team |

---

## Required Screenshots

Screenshots to capture during demo execution of this guide:

| # | Screen | Filename | Content |
|---|--------|----------|---------|
| 1 | Datadog Logs | `datadog-arp-detection.png` | Search results for `source:fsxn-ems arw.volume.state` |
| 2 | Datadog Log Detail | `datadog-arp-log-detail.png` | ARP event with expanded structured attributes |
| 3 | CloudWatch Logs | `aws-ems-lambda-logs.png` | EMS Lambda execution logs (success) |
| 4 | Datadog FPolicy | `datadog-fpolicy-suspect-activity.png` | Suspect file operation FPolicy logs |
| 5 | ONTAP CLI | `ontap-arp-status.png` | Output of `security anti-ransomware volume show` |
| 6 | ONTAP CLI | `ontap-arp-snapshot.png` | ARP snapshot listing |

---

## References

- [AWS Docs: Protecting your data with ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html)
- [AWS Docs: Responding to ARP alerts](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/respond-ARP.html)
- [AWS Docs: Understanding EMS alerts for ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/EMS-ARP.html)
- [AWS Blog: Protecting data using ARP on FSx for ONTAP](https://aws.amazon.com/blogs/storage/protecting-data-using-autonomous-ransomware-protection-on-amazon-fsx-for-netapp-ontap/)
- [NetApp Docs: Restore data from ARP snapshots](https://docs.netapp.com/us-en/ontap/anti-ransomware/recover-data-task.html)
- [NetApp Docs: Respond to abnormal activity](https://docs.netapp.com/us-en/ontap/anti-ransomware/respond-abnormal-task.html)
- [NetApp KB: Ransomware prevention and recovery](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Ransomware_prevention_and_recovery_in_ONTAP)

---

## Related Documents

- [Automated Incident Response Guide](automated-response-guide.md) — Automated user/IP blocking triggered by ARP detection
- [EMS Detection Capabilities](ems-detection-capabilities.md) — Full EMS event catalog including ARP events
- [Demo Runbook: Automated Response](demo-automated-response.md) — Step-by-step demo including ARP → auto-block flow
- [Security Monitoring Index](security-monitoring-index.md) — Navigation across all security documents
