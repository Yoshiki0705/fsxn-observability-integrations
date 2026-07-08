# Automated Response — Screenshot Evidence Specification

## Purpose

Screenshots required for E2E verification of the automated incident response feature.
Used in: Blog Part 18, live demos, internal documentation.

## Required Screenshots (20 total)

### Phase 1: Deployment (1 screenshot)

| # | Filename | Content | How to Capture |
|---|----------|---------|---------------|
| 1 | `01-cfn-stack-outputs.png` | CloudFormation stack outputs table showing TriggerTopicArn and NotificationTopicArn | AWS Console → CloudFormation → fsxn-automated-response → Outputs tab |

### Phase 2: SMB User Blocking (5 screenshots)

| # | Filename | Content | How to Capture |
|---|----------|---------|---------------|
| 2 | `02-smb-access-before.png` | Terminal showing successful `ls`, `cat`, `echo` on SMB share by test user | SMB client terminal |
| 3 | `03-sns-publish-block-smb.png` | CLI helper output or `aws sns publish` returning MessageId | Local terminal |
| 4 | `04-lambda-log-block-smb.png` | CloudWatch Logs with "Blocking SMB user" log line and request ID | AWS Console → CloudWatch → Log groups → /aws/lambda/fsxn-automated-response-handler |
| 5 | `05-ontap-name-mapping-blocked.png` | ONTAP CLI output of `vserver name-mapping show` with DOMAIN\\user → " " | SSH to ONTAP mgmt |
| 6 | `06-smb-access-denied.png` | Terminal showing "Permission denied" or "Access denied" for the blocked user | SMB client terminal |
| 7 | `07-smb-access-restored.png` | Terminal showing successful access after unblock | SMB client terminal |

### Phase 3: NFS IP Blocking (4 screenshots)

| # | Filename | Content | How to Capture |
|---|----------|---------|---------------|
| 8 | `08-nfs-access-before.png` | Terminal showing successful `ls`, `touch` on NFS mount | NFS client terminal |
| 9 | `09-sns-publish-block-nfs.png` | CLI helper output for NFS IP block | Local terminal |
| 10 | `10-ontap-export-policy-blocked.png` | ONTAP CLI output showing export-policy rule with `fsxn_auto_response` marker | SSH to ONTAP mgmt |
| 11 | `11-nfs-access-denied.png` | Terminal showing NFS access failure after IP block | NFS client terminal |

### Phase 4: Full Containment — ARP (6 screenshots)

| # | Filename | Content | How to Capture |
|---|----------|---------|---------------|
| 12 | `12-ontap-arp-active.png` | ONTAP `security anti-ransomware volume show` output with "active" state | SSH to ONTAP mgmt |
| 13 | `13-ontap-arp-simulate.png` | ONTAP `security anti-ransomware volume attack simulate` command and output | SSH to ONTAP mgmt |
| 14 | `14-lambda-ems-arp-event.png` | EMS Lambda CloudWatch log showing `arw.volume.state` event received | AWS Console → CloudWatch Logs |
| 15 | `15-lambda-containment-steps.png` | Response Lambda log showing all 3 steps: snapshot created + user blocked + sessions disconnected | AWS Console → CloudWatch Logs |
| 16 | `16-ontap-incident-snapshot.png` | ONTAP `volume snapshot show` with `incident_response_*` snapshot visible | SSH to ONTAP mgmt |
| 17 | `17-email-notification-containment.png` | Email inbox showing containment notification with JSON result body | Email client |

### Phase 5: TTL Auto-Unblock (2 screenshots)

| # | Filename | Content | How to Capture |
|---|----------|---------|---------------|
| 18 | `18-lambda-ttl-cleanup.png` | TTL cleanup Lambda log showing "TTL expired — removed SMB block" | AWS Console → CloudWatch Logs |
| 19 | `19-ontap-ttl-cleared.png` | ONTAP `vserver name-mapping show` with empty results (block auto-removed) | SSH to ONTAP mgmt |

### Phase 6: Operational Status (1 screenshot)

| # | Filename | Content | How to Capture |
|---|----------|---------|---------------|
| 20 | `20-ontap-active-blocks-status.png` | Combined output of name-mapping + export-policy rule shows (current state) | SSH to ONTAP mgmt |

---

## Masking Requirements

Before committing screenshots, run the masking script:

```bash
python3 docs/screenshots/mask_screenshots.py
```

Mask the following in all screenshots:
- Real AWS Account IDs → replace with `123456789012`
- Real IP addresses → replace with `10.0.x.x` pattern
- Real SVM names → OK to keep (not PII)
- Real usernames → replace with `test-user` or `jdoe`
- Real Secret ARNs → mask the suffix after `secret:`
- Email addresses → mask with `admin@example.com`

---

## Blog Cover Image

| Filename | Content | Dimensions |
|----------|---------|-----------|
| `cover-18-automated-response.png` | Architecture diagram (Detection → SNS → Lambda → ONTAP blocks) | 1600×840 |

Create using draw.io or similar. Key elements:
- Left side: detection sources (CloudWatch Alarm, SIEM, EMS Webhook)
- Center: SNS → Lambda
- Right side: ONTAP actions (name-mapping block, export-policy deny, snapshot)
- Color scheme: AWS orange + navy

---

## Verification Criteria

A screenshot is valid for E2E evidence if it shows:
- [ ] Timestamp visible (proves recency)
- [ ] Relevant data visible (not truncated)
- [ ] No real PII/account IDs visible (masked)
- [ ] Consistent SVM/volume names across all screenshots (same demo session)
- [ ] Sequential timestamps proving causal order (block before deny)
