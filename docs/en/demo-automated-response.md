# Automated Response Demo Runbook

🌐 [日本語](../ja/demo-automated-response.md) | **English** (this page)

## Purpose

Step-by-step procedure for demonstrating the automated incident response feature end-to-end. Covers: deploy → trigger detection → verify auto-block → confirm access denial → unblock → confirm restored access.

Use this runbook for:
- Live demos (in-person or recorded)
- E2E verification before blog publication
- Internal training

---

## Prerequisites

| Item | Requirement |
|------|------------|
| FSx for ONTAP | Running, with ARP enabled on at least one volume |
| VPC access | Lambda subnet can reach ONTAP management IP (TCP 443) |
| ONTAP credentials | `fsxadmin` username/password in Secrets Manager |
| SMB client | Windows or Linux host mounted to the SVM via CIFS |
| NFS client | Linux host mounted to the SVM via NFS |
| AWS CLI | Configured with appropriate IAM permissions |
| jq | Installed for JSON formatting |

---

## Phase 1: Deploy the Automated Response Stack

### Step 1.1: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=<secret-arn> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    DefaultSvmName=<svm-name> \
    NotificationEmail=<your-email> \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 1.2: Verify Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-automated-response \
  --query 'Stacks[0].Outputs' \
  --output table
```

📸 **Screenshot 1**: CloudFormation stack outputs showing TriggerTopicArn and NotificationTopicArn

### Step 1.3: Set CLI Environment

```bash
export RESPONSE_TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-automated-response \
  --query 'Stacks[0].Outputs[?OutputKey==`TriggerTopicArn`].OutputValue' \
  --output text)

export DEFAULT_SVM="<svm-name>"
echo "Topic: $RESPONSE_TOPIC_ARN"
```

---

## Phase 2: Demonstrate SMB User Blocking

### Step 2.1: Verify Current Access (Before Block)

From the SMB client, confirm normal access:

```bash
# On SMB client (as the test user)
ls //fsxn-share/test-data/
cat //fsxn-share/test-data/sample-file.txt
echo "write test" > //fsxn-share/test-data/write-test.txt
```

📸 **Screenshot 2**: Terminal showing successful file operations (ls, read, write) by test user

### Step 2.2: Trigger SMB User Block

```bash
# Using CLI helper
./shared/scripts/automated-response-cli.sh block-smb \
  --domain <DOMAIN> --user <test-user> \
  --reason "Demo: simulated insider threat"

# Or directly via SNS
aws sns publish \
  --topic-arn "$RESPONSE_TOPIC_ARN" \
  --message '{
    "action": "block_smb_user",
    "svm_name": "'$DEFAULT_SVM'",
    "domain": "<DOMAIN>",
    "username": "<test-user>",
    "reason": "Demo: simulated insider threat"
  }'
```

📸 **Screenshot 3**: CLI output showing successful SNS publish (MessageId returned)

### Step 2.3: Verify Lambda Execution

```bash
# Wait 10-15 seconds for Lambda to execute
sleep 15

# Check Lambda logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-automated-response-handler \
  --start-time $(date -v-2M +%s000 2>/dev/null || date -d '2 minutes ago' +%s000) \
  --filter-pattern "block_smb_user" \
  --query 'events[*].message' \
  --output text | tail -5
```

📸 **Screenshot 4**: CloudWatch Logs showing Lambda execution with "Blocking SMB user" log line

### Step 2.4: Verify Block on ONTAP

```bash
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
```

📸 **Screenshot 5**: ONTAP CLI showing name-mapping entry (DOMAIN\\user → " ")

### Step 2.5: Verify Access Denied (After Block)

From the SMB client, confirm access is denied:

```bash
# On SMB client (as the blocked test user)
ls //fsxn-share/test-data/
# → Expected: Permission denied / Access denied

cat //fsxn-share/test-data/sample-file.txt
# → Expected: Permission denied
```

📸 **Screenshot 6**: Terminal showing "Permission denied" or "Access denied" for the blocked user

### Step 2.6: Unblock User

```bash
./shared/scripts/automated-response-cli.sh unblock-smb \
  --domain <DOMAIN> --user <test-user>
```

### Step 2.7: Verify Access Restored

```bash
# On SMB client (may need to reconnect)
net use \\\\fsxn-share /delete 2>/dev/null
net use \\\\fsxn-share /user:<DOMAIN>\\<test-user> <password>
ls //fsxn-share/test-data/
# → Expected: Success
```

📸 **Screenshot 7**: Terminal showing restored access after unblock

---

## Phase 3: Demonstrate NFS IP Blocking

### Step 3.1: Verify Current NFS Access

```bash
# On NFS client
ls /mnt/fsxn/test-data/
touch /mnt/fsxn/test-data/nfs-write-test.txt
```

📸 **Screenshot 8**: Terminal showing successful NFS file operations

### Step 3.2: Trigger NFS IP Block

```bash
# Get the NFS client IP
CLIENT_IP=$(hostname -I | awk '{print $1}')
echo "Blocking IP: $CLIENT_IP"

./shared/scripts/automated-response-cli.sh block-nfs \
  --ip "$CLIENT_IP" \
  --reason "Demo: simulated mass deletion from suspicious IP"
```

📸 **Screenshot 9**: CLI output showing NFS IP block published

### Step 3.3: Verify Block on ONTAP

```bash
ssh fsxadmin@<management-ip> "export-policy rule show -clientmatch *fsxn_auto_response*"
```

📸 **Screenshot 10**: ONTAP CLI showing export-policy rule with fsxn_auto_response marker

### Step 3.4: Verify NFS Access Denied

```bash
# On NFS client (may require remount or cache expiry)
umount /mnt/fsxn && mount -t nfs <svm-nfs-lif>:/vol_data /mnt/fsxn
ls /mnt/fsxn/test-data/
# → Expected: Permission denied or mount failure
```

> **NFS Cache Note**: Linux NFS clients cache access decisions for up to 60 seconds (`actimeo` default). After blocking, you may need to wait up to 60s or remount with `mount -o actimeo=0` (test only) for the deny to take effect immediately.

📸 **Screenshot 11**: Terminal showing NFS access denied after IP block

### Step 3.5: Unblock IP

```bash
./shared/scripts/automated-response-cli.sh unblock-nfs --ip "$CLIENT_IP"
```

---

## Phase 4: Demonstrate Full Containment (ARP → Auto-Block)

### Step 4.1: Verify ARP is Active

```bash
ssh fsxadmin@<management-ip> "security anti-ransomware volume show -vserver $DEFAULT_SVM"
```

📸 **Screenshot 12**: ONTAP showing ARP in "active" state on target volume

### Step 4.2: Connect EMS Webhook to Response Pipeline

Ensure the EMS webhook delivers to Datadog/SIEM, and the SIEM monitor can publish to the response SNS topic. If using CloudWatch Log Alarm path:

```bash
# Verify syslog delivery is active
aws logs filter-log-events \
  --log-group-name /syslog/fsxn-admin-audit \
  --start-time $(date -v-5M +%s000 2>/dev/null || date -d '5 minutes ago' +%s000) \
  --limit 3 \
  --query 'events[*].message' --output text
```

### Step 4.3: Simulate Ransomware (TEST ENVIRONMENT ONLY)

```bash
# CAUTION: Only in test environment with disposable data
ssh fsxadmin@<management-ip> \
  "security anti-ransomware volume attack simulate -vserver $DEFAULT_SVM -volume <test-vol>"
```

📸 **Screenshot 13**: ONTAP CLI showing ARP attack simulation command

### Step 4.4: Observe Detection Chain

Wait ~30 seconds for EMS event delivery:

```bash
# Check EMS webhook arrival in CloudWatch (Lambda logs)
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-ems-fpolicy-handler \
  --start-time $(date -v-2M +%s000 2>/dev/null || date -d '2 minutes ago' +%s000) \
  --filter-pattern "arw.volume.state" \
  --query 'events[*].message' --output text
```

📸 **Screenshot 14**: Lambda log showing `arw.volume.state` EMS event received

### Step 4.5: Trigger Full Containment

If the SIEM monitor auto-triggers SNS, this happens automatically. For manual demo:

```bash
./shared/scripts/automated-response-cli.sh contain-smb \
  --domain <DOMAIN> --user <suspect-user> \
  --volume <test-vol> \
  --reason "ARP detection - arw.volume.state alert"
```

### Step 4.6: Verify Containment Result

```bash
# Check Lambda execution
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-automated-response-handler \
  --start-time $(date -v-2M +%s000 2>/dev/null || date -d '2 minutes ago' +%s000) \
  --filter-pattern "contain_smb_threat" \
  --query 'events[*].message' --output text
```

📸 **Screenshot 15**: Lambda log showing all 3 containment steps (snapshot + block + disconnect)

### Step 4.7: Verify Snapshot Created

```bash
ssh fsxadmin@<management-ip> \
  "volume snapshot show -vserver $DEFAULT_SVM -volume <test-vol> -snapshot incident_response_*"
```

📸 **Screenshot 16**: ONTAP showing incident_response snapshot with timestamp

### Step 4.8: Verify SNS Notification Received

📸 **Screenshot 17**: Email notification showing containment result JSON (from notification topic)

---

## Phase 5: Demonstrate TTL Auto-Unblock

### Step 5.1: Deploy TTL Stack

```bash
aws cloudformation deploy \
  --template-file shared/templates/automated-response-ttl.yaml \
  --stack-name fsxn-automated-response-ttl \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=<secret-arn> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    DefaultSvmName=$DEFAULT_SVM \
    BlockTtlMinutes=5 \
    CheckIntervalMinutes=1 \
    NotificationTopicArn=<notification-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 5.2: Create a Block

```bash
./shared/scripts/automated-response-cli.sh block-smb \
  --domain <DOMAIN> --user <test-user> \
  --reason "TTL demo - will auto-expire in 5 minutes"
```

### Step 5.3: Wait for TTL Expiry

```bash
echo "Block created. TTL cleanup Lambda runs every 1 minute."
echo "Block will be removed within ~5 minutes."
echo "Watch CloudWatch Logs (timeout after 7 minutes)..."

# Monitor cleanup Lambda (with timeout to avoid waiting forever)
timeout 420 aws logs tail /aws/lambda/fsxn-automated-response-ttl-cleanup --follow
# If timeout reached without seeing removal, check Lambda errors:
# aws logs filter-log-events --log-group-name /aws/lambda/fsxn-automated-response-ttl-cleanup --filter-pattern "ERROR"
```

> **Note**: The TTL cleanup currently removes ALL blocks with the `fsxn_auto_response` marker on each run. It does not track individual block creation times. For production, consider implementing a DynamoDB tracking table.

📸 **Screenshot 18**: CloudWatch Logs showing "TTL expired — removed SMB block" message

### Step 5.4: Verify Auto-Unblock

```bash
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
# → Expected: no entries (block auto-removed)
```

📸 **Screenshot 19**: ONTAP showing empty name-mapping (block auto-removed by TTL)

---

## Phase 6: List Active Blocks (Operational Visibility)

```bash
# Direct ONTAP CLI check
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
ssh fsxadmin@<management-ip> "export-policy rule show -clientmatch *fsxn_auto_response*"
```

📸 **Screenshot 20**: ONTAP showing current state of all active blocks (or empty if all cleared)

---

## Screenshot Summary

| # | Content | Filename | Phase |
|---|---------|----------|-------|
| 1 | CloudFormation stack outputs | `01-cfn-stack-outputs.png` | Deploy |
| 2 | SMB access working (before block) | `02-smb-access-before.png` | SMB Block |
| 3 | SNS publish success (MessageId) | `03-sns-publish-block-smb.png` | SMB Block |
| 4 | Lambda log: "Blocking SMB user" | `04-lambda-log-block-smb.png` | SMB Block |
| 5 | ONTAP name-mapping entry | `05-ontap-name-mapping-blocked.png` | SMB Block |
| 6 | SMB access denied (after block) | `06-smb-access-denied.png` | SMB Block |
| 7 | SMB access restored (after unblock) | `07-smb-access-restored.png` | SMB Block |
| 8 | NFS access working (before block) | `08-nfs-access-before.png` | NFS Block |
| 9 | SNS publish success (NFS block) | `09-sns-publish-block-nfs.png` | NFS Block |
| 10 | ONTAP export-policy rule with marker | `10-ontap-export-policy-blocked.png` | NFS Block |
| 11 | NFS access denied (after block) | `11-nfs-access-denied.png` | NFS Block |
| 12 | ONTAP ARP active state | `12-ontap-arp-active.png` | Full Containment |
| 13 | ARP attack simulate command | `13-ontap-arp-simulate.png` | Full Containment |
| 14 | Lambda log: arw.volume.state received | `14-lambda-ems-arp-event.png` | Full Containment |
| 15 | Lambda log: contain_smb_threat steps | `15-lambda-containment-steps.png` | Full Containment |
| 16 | ONTAP incident_response snapshot | `16-ontap-incident-snapshot.png` | Full Containment |
| 17 | Email notification (containment result) | `17-email-notification-containment.png` | Full Containment |
| 18 | Lambda log: TTL expired auto-remove | `18-lambda-ttl-cleanup.png` | TTL |
| 19 | ONTAP empty name-mapping (auto-cleared) | `19-ontap-ttl-cleared.png` | TTL |
| 20 | ONTAP active blocks summary | `20-ontap-active-blocks-status.png` | Operational |

---

## Cleanup

```bash
# Remove all test blocks
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
# Delete any remaining entries manually

# Delete test snapshots
ssh fsxadmin@<management-ip> "volume snapshot delete -vserver $DEFAULT_SVM -volume <test-vol> -snapshot incident_response_*"

# Delete CloudFormation stacks (optional)
aws cloudformation delete-stack --stack-name fsxn-automated-response-ttl
aws cloudformation delete-stack --stack-name fsxn-automated-response
```

---

## Timing Reference

| Phase | Duration | Notes |
|-------|----------|-------|
| Phase 1 (Deploy) | ~5 min | CloudFormation deploy |
| Phase 2 (SMB Block) | ~3 min | Block + verify + unblock |
| Phase 3 (NFS Block) | ~3 min | Block + verify + unblock |
| Phase 4 (Full Containment) | ~5 min | ARP simulate + containment |
| Phase 5 (TTL) | ~7 min | Deploy + wait for TTL expiry |
| Phase 6 (Operational) | ~1 min | Status check |
| **Total** | **~24 min** | Full demo with all phases |

For a shorter demo (meeting): Phase 1 + Phase 2 + Phase 4 = ~13 minutes.

---

## Related Documents

- [Automated Response Guide](automated-response-guide.md)
- [ARP Incident Response Guide](arp-incident-response-guide.md)
- [EMS Detection Capabilities](ems-detection-capabilities.md)
- [Demo Scenarios (all vendors)](demo-scenarios.md)
- [CLI Helper](../../shared/scripts/automated-response-cli.sh)
