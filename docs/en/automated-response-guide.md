# Automated Incident Response Guide — User/IP Blocking via ONTAP REST API

## Executive Summary

This guide describes how to implement automated threat containment for Amazon FSx for NetApp ONTAP using AWS-native detection services combined with ONTAP REST API response actions. The approach delivers the same containment capabilities — user blocking, IP blocking, and protective snapshots — available in dedicated storage security products, while keeping detection and orchestration within the AWS ecosystem and third-party observability platforms.

**Key capabilities:**
- Block compromised SMB users via ONTAP name-mapping (access denied across all volumes)
- Block attacker IPs from NFS access via export-policy rules
- Create protective snapshots for evidence preservation (with storm-prevention cooldown)
- Disconnect active CIFS sessions to immediately cut off a compromised user
- Composite containment actions that execute all steps in sequence

**Detection sources (any combination):**
- CloudWatch Log Alarm (admin audit log anomalies)
- EMS Webhook (ARP ransomware detection, quota events)
- FPolicy analytics (mass deletion, abnormal extension changes)
- Third-party SIEM monitors (Datadog, Splunk, Elastic, etc.)

---

## Architecture

```
+-------------------------------------------------------------------+
| Detection Layer (AWS-native + SaaS Observability)                 |
+-------------------------------------------------------------------+
|                                                                   |
|  CloudWatch Log Alarm --+                                         |
|  EMS Webhook -> Monitor-+                                         |
|  FPolicy -> SIEM -------+-- SNS Trigger Topic                     |
|  Manual invocation -----+                                         |
|                                                                   |
+-------------------------------------------------------------------+
| Response Layer (Lambda + ONTAP REST API)                          |
+-------------------------------------------------------------------+
|                                                                   |
|  SNS -> Lambda (VPC) -> ONTAP REST API                            |
|           |                                                       |
|           +-> Block SMB user (name-mapping)                       |
|           +-> Block NFS IP (export-policy rule)                   |
|           +-> Create protective snapshot                          |
|           +-> Disconnect CIFS sessions                            |
|           +-> SNS notification (action result)                    |
|                                                                   |
|  DLQ -> Alarm -> Notification (failed actions)                    |
|                                                                   |
+-------------------------------------------------------------------+
```

---

## How Blocking Works

### SMB User Blocking

The mechanism uses ONTAP name-mapping to deny access:

| Step | What Happens | ONTAP Equivalent |
|------|-------------|-----------------|
| 1 | Lambda receives trigger with domain + username | — |
| 2 | Creates a name-mapping: `DOMAIN\user` → `" "` (empty) | `vserver name-mapping create -direction win-unix -pattern "DOMAIN\\user" -replacement " "` |
| 3 | User's next file operation is denied | SID-to-UNIX translation fails → access denied |
| 4 | All SVM volumes affected | Name-mapping applies SVM-wide |

**Scope**: The block applies to the entire SVM. All volumes, shares, and exports within the SVM deny access to the blocked user.

**Reversal**: Delete the name-mapping entry to restore access.

### NFS IP Blocking

The mechanism adds a deny rule to the export policy:

| Step | What Happens | ONTAP Equivalent |
|------|-------------|-----------------|
| 1 | Lambda receives trigger with client IP | — |
| 2 | Creates export-policy rule: `clientmatch=<marker>,<ip>`, `ro_rule=never`, `rw_rule=never` | `export-policy rule create -clientmatch "fsxn_auto_response,<ip>" -rorule never -rwrule never` |
| 3 | Rule inserted at position 1 (highest priority) | Evaluated before allow rules |
| 4 | Client IP blocked from all NFS access on that policy | — |

**Scope**: Affects all volumes using the specified export policy.

**Marker**: Rules include `fsxn_auto_response` in the client match field, making them easy to identify and clean up.

**Reversal**: Delete export-policy rules containing the response marker.

### CIFS Session Disconnect

Forcefully terminates active sessions so the blocked user cannot continue operations until their access is revoked:

- Lists active CIFS sessions matching user or IP
- Deletes each session via REST API
- Used in combination with user blocking for immediate effect

---

## Comparison: This Approach vs Dedicated Storage Security Products

Dedicated storage security products (such as DII Storage Workload Security) provide ML-based behavioral analytics with integrated containment. This project achieves equivalent containment using AWS-native and SaaS detection with ONTAP REST API response:

| Capability | Dedicated Product | This Approach |
|-----------|------------------|---------------|
| SMB user blocking | ✅ Automated | ✅ Automated (same ONTAP API) |
| NFS IP blocking | ✅ Automated | ✅ Automated (same ONTAP API) |
| Protective snapshot | ✅ Automated | ✅ Automated (with cooldown) |
| Session disconnect | ✅ Automated | ✅ Automated |
| User behavior ML | ✅ Built-in (per-user baselines) | Via SIEM (Datadog ML Anomaly, Elastic ML Jobs, etc.) |
| AD user tracking | ✅ Built-in collector | Via FPolicy logs (user field) + AD lookup |
| Detection scope | Storage only | Storage + network + application (broader context) |
| Data residency | SaaS (external) | AWS Region (data stays in your VPC) |
| Integration with SIEM | Limited export | Native (detection originates from SIEM) |
| Cost model | Per-node license | Pay-per-use (Lambda invocations) |

> **Storage Operations lens**: The underlying ONTAP mechanisms are identical — both approaches use the same REST API endpoints. The difference is where detection intelligence lives. Dedicated products embed ML in their SaaS; this approach delegates detection to the customer's chosen observability platform.

> **Security Architect lens**: AWS-native detection provides broader attack context (VPC Flow Logs, CloudTrail, GuardDuty findings) that storage-only solutions cannot correlate. For organizations with existing SIEM investments, this is a natural extension of their security operations workflow.

---

## Prerequisites

### ONTAP Version

- **FSx for ONTAP**: All currently supported versions (ONTAP 9.11.1+)
- **Name-mapping REST API**: Available from ONTAP 9.6+
- **Export-policy REST API**: Available from ONTAP 9.6+
- **CIFS sessions REST API**: Available from ONTAP 9.8+
- **ARP (Autonomous Ransomware Protection)**: ONTAP 9.10.1+ (learning mode), 9.13.1+ (ARP/AI)

### ONTAP Permissions

The Lambda execution role connects to ONTAP with `fsxadmin` credentials stored in Secrets Manager. The following ONTAP operations are used:

```
# Required permissions (fsxadmin has these by default)
- GET /api/svm/svms
- GET /api/storage/volumes
- POST /api/storage/volumes/{uuid}/snapshots
- GET/POST/DELETE /api/name-services/name-mappings
- GET/POST/DELETE /api/protocols/nfs/export-policies/{id}/rules
- GET/DELETE /api/protocols/cifs/sessions
```

### Network Access

The Lambda function must be deployed in a VPC with:
- Private subnet with route to ONTAP management endpoint
- Security Group allowing HTTPS (TCP 443) outbound to ONTAP management IP
- No NAT Gateway required (ONTAP endpoint is private)

#### Network Prerequisites Checklist

| Requirement | How to Verify |
|------------|---------------|
| Lambda subnet has route to ONTAP mgmt IP | `aws ec2 describe-route-tables` — verify route to ONTAP CIDR |
| Security Group allows TCP 443 egress | SG outbound rule: `TCP 443 → <ONTAP-mgmt-IP>/32` |
| ONTAP management LIF is UP | `network interface show -role cluster-mgmt` (SSH to ONTAP) |
| DNS resolution (if using hostname) | Typically not needed (use IP directly for FSx for ONTAP) |
| Cross-VPC (if applicable) | VPC peering or Transit Gateway route + SG reference |
| Same-VPC different subnet | Ensure no NACL blocking TCP 443 between subnets |

> **TLS Note**: The default module configuration disables certificate verification (`CERT_NONE`). For production, retrieve the FSx for ONTAP CA certificate and pass it via `CA_CERT_PATH` environment variable. Get the cert via: `security certificate show -type root-ca -vserver <svm>` (ONTAP CLI).

### Secrets Manager

Store ONTAP credentials as JSON:
```json
{
  "username": "fsxadmin",
  "password": "<your-password>"
}
```

---

## Deployment

### Deploy the CloudFormation Stack

```bash
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=arn:aws:secretsmanager:<region>:<account>:secret:<name> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    DefaultSvmName=<svm-name> \
    NotificationEmail=admin@example.com \
  --capabilities CAPABILITY_NAMED_IAM
```

### Connect Detection Sources

After deployment, subscribe the trigger SNS topic to your detection sources:

**CloudWatch Log Alarm → SNS:**
```bash
# The Log Alarm's action points to the trigger topic
# (configured during Log Alarm creation)
```

**Datadog Monitor → SNS:**
```
Use Datadog's @sns-<topic-name> notification in monitor message
```

**Manual test invocation:**
```bash
aws sns publish \
  --topic-arn <TriggerTopicArn from stack outputs> \
  --message '{
    "action": "contain_smb_threat",
    "svm_name": "svm-prod-01",
    "domain": "CORP",
    "username": "test-user",
    "volume_name": "vol_data",
    "reason": "Manual test"
  }'
```

---

## Supported Actions

### Individual Actions

| Action | Required Fields | Description |
|--------|----------------|-------------|
| `block_smb_user` | svm_name, domain, username | Block SMB user via name-mapping |
| `unblock_smb_user` | svm_name, domain, username | Remove SMB user block |
| `block_nfs_ip` | svm_name, client_ip | Block IP via export-policy rule |
| `unblock_nfs_ip` | svm_name, client_ip | Remove IP block |
| `create_snapshot` | svm_name, volume_name | Create protective snapshot |

### Composite Actions (Multi-Step)

| Action | Steps | Use Case |
|--------|-------|----------|
| `contain_smb_threat` | Snapshot → Block user → Disconnect sessions | Compromised AD user detected |
| `contain_nfs_threat` | Snapshot → Block IP | Suspicious NFS client activity |

---

## SNS Message Format

### Basic Format (minimum required)

```json
{
  "action": "contain_smb_threat",
  "svm_name": "svm-prod-01",
  "domain": "CORP",
  "username": "jdoe",
  "volume_name": "vol_data",
  "reason": "ARP ransomware detection - arw.volume.state alert"
}
```

### Extended Format (recommended for compliance/audit)

```json
{
  "action": "contain_smb_threat",
  "svm_name": "svm-prod-01",
  "domain": "CORP",
  "username": "jdoe",
  "volume_name": "vol_data",
  "policy_name": "default",
  "reason": "ARP ransomware detection - arw.volume.state alert",
  "incident_id": "INC-2026-0708-001",
  "detection_source": "datadog-monitor-fsxn-arp",
  "severity": "critical",
  "trigger_id": "msg-abc123-def456"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| action | Yes | One of the supported action names |
| svm_name | Yes (or set DEFAULT_SVM_NAME) | Target SVM |
| domain | SMB actions | Windows domain name |
| username | SMB actions | Windows username |
| client_ip | NFS actions | Client IP address |
| volume_name | Snapshot / composite | Volume to protect |
| policy_name | NFS actions | Export policy (default: "default") |
| reason | Yes (blocking actions) | Human-readable reason (logged) |
| incident_id | No (recommended) | External incident tracking ID (e.g., PagerDuty, ServiceNow) |
| detection_source | No (recommended) | Which system detected the threat (for forensic correlation) |
| severity | No (recommended) | `critical` / `high` / `medium` / `low` |
| trigger_id | No | SNS MessageId or upstream correlation ID |

> **Compliance lens (HIPAA/FISC/SOC2)**: For regulated environments, always include `incident_id`, `detection_source`, and `severity`. These fields are passed through to CloudWatch Logs and notification messages, forming the audit trail.

---

## Integration Examples

### Severity-Based Routing (Critical — Prevents False-Positive Lockouts)

ARP emits events at two severity levels. **Only auto-block on `alert` (high confidence)**:

| ARP Severity | Confidence | Recommended Action | Rationale |
|-------------|-----------|-------------------|-----------|
| `alert` | High (file tampering + encryption confirmed) | ✅ Auto-contain (`contain_smb_threat`) | High confidence, damage in progress |
| `warning` | Moderate (suspicious but unconfirmed) | ⚠️ Notify only (do NOT auto-block) | May be false positive during learning period |

> **ARP Learning Period**: ARP requires 30 days to establish a behavioral baseline. During this period, `warning` events are common and often benign (bulk file conversions, backup software). Auto-blocking on `warning` during learning will disrupt legitimate users.

**Detection rule configuration example (Datadog Monitor)**:
```
# Auto-contain: ONLY severity=alert
source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.severity:alert
→ Trigger: contain_smb_threat via SNS

# Notify only: severity=warning
source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.severity:warning
→ Trigger: Slack/PagerDuty notification (investigation only)
```

### Example 1: CloudWatch Log Alarm → Auto-Block

When the admin audit log shows 10+ failed login attempts in 5 minutes:

```
CloudWatch Log Alarm (query: failed logins > 10)
  → SNS (Trigger Topic)
  → Lambda
  → ONTAP: block_smb_user + create_snapshot
  → SNS notification to security team
```

### Example 2: Datadog ARP Monitor → Full Containment

When Datadog receives an ARP EMS event and the monitor fires:

```
ONTAP ARP → EMS Webhook → Datadog
  → Datadog Monitor fires
  → Workflow → SNS publish (contain_smb_threat)
  → Lambda → ONTAP: snapshot + block + disconnect
  → PagerDuty escalation
```

### Example 3: FPolicy Mass Deletion → IP Block

When FPolicy analytics detect >50 deletes/5min from a single IP:

```
FPolicy → SQS → Lambda → Datadog/Elastic
  → SIEM rule fires (mass deletion threshold)
  → SNS publish (contain_nfs_threat)
  → Lambda → ONTAP: snapshot + block IP
```

---

## Operational Procedures

### Viewing Blocked Users/IPs

```bash
# SSH to FSx for ONTAP management endpoint
ssh fsxadmin@<management-ip>

# List blocked SMB users (name-mappings with empty replacement)
vserver name-mapping show -direction win-unix -replacement " "

# List blocked NFS IPs (rules with our marker)
export-policy rule show -clientmatch *fsxn_auto_response*
```

### Manual Unblock

Via SNS message:
```bash
aws sns publish \
  --topic-arn <TriggerTopicArn> \
  --message '{"action":"unblock_smb_user","svm_name":"svm-prod-01","domain":"CORP","username":"jdoe"}'
```

Via ONTAP CLI (emergency):
```bash
# Unblock SMB user
vserver name-mapping delete -direction win-unix -position <position>

# Unblock NFS IP
export-policy rule delete -vserver <svm> -policyname <policy> -ruleindex <index>
```

### Monitoring

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| DLQ depth | CloudWatch (auto-created alarm) | > 0 messages |
| Lambda errors | CloudWatch Lambda metrics | > 0 in 5 min |
| Response latency | Lambda Duration metric | p95 > 10s |
| Active blocks | Custom metric (optional) | Tracking only |

---

## Security Considerations

- **Least privilege**: The Lambda role only has access to Secrets Manager (read), SNS (publish), and VPC network access to ONTAP. No broad IAM permissions.
- **Credential rotation**: Use Secrets Manager auto-rotation for ONTAP credentials.
- **Audit trail**: All actions are logged in CloudWatch Logs with correlation IDs.
- **Cooldown protection**: Snapshot creation has a configurable cooldown (default 15 min) to prevent storage exhaustion during sustained attacks.
- **Marker-based cleanup**: All response rules include `fsxn_auto_response` marker for safe identification and bulk removal.
- **Time-limited blocks**: Implement a scheduled Lambda to auto-remove blocks after a configurable duration (similar to DII's time-limited access restriction).

---

## Cost Estimate

| Component | Monthly Cost (typical) | Notes |
|-----------|----------------------|-------|
| Lambda | ~$0.10 | <100 invocations/month (incident response only) |
| SNS | ~$0.01 | Low message volume |
| Secrets Manager | ~$0.40 | 1 secret |
| VPC ENI | $0 (Lambda VPC) | Shared with existing VPC |
| **Total** | **~$0.51/month** | Excludes VPC/NAT costs (shared) |

### Cost at Scale

| Incident Volume | Lambda Cost | CW Logs Cost | SNS Cost | Total |
|----------------|-------------|-------------|----------|-------|
| 10/month | $0.01 | $0.03 | $0.01 | ~$0.45 + Secrets Manager |
| 100/month | $0.05 | $0.30 | $0.01 | ~$0.76 |
| 1,000/month | $0.50 | $3.00 | $0.05 | ~$3.95 |
| 10,000/month | $5.00 | $30.00 | $0.50 | ~$35.90 |

> At 10,000 incidents/month (extreme volume — likely indicates misconfigured detection thresholds), total cost remains under $40. The VPC Lambda cold start cost is negligible because Lambda ENIs are reused across invocations.

### Production Deployment Note

The CloudFormation template embeds Lambda code as `ZipFile` for quickstart deployment. For production GitOps workflows:
1. Package `ontap_response.py` as a Lambda Layer (`shared/python/` directory structure)
2. Use `CodeUri` with S3 bucket instead of `ZipFile`
3. Version the Layer independently from the CloudFormation stack
4. CI/CD pipeline: `pytest` → package Layer → deploy → integration test

---

## Related Documents

- [ARP Incident Response Guide](arp-incident-response-guide.md)
- [EMS Webhook Setup](../integrations/datadog/docs/en/ems-webhook-setup.md)
- [FPolicy Operations](operational-notes-fpolicy.md)
- [Pipeline SLO](pipeline-slo.md)
- [CloudWatch Log Alarm Guide](syslog-vpce-setup-guide.md)

---

## Troubleshooting

### Lambda Execution Failures

| Symptom | Cause | Solution |
|---------|-------|----------|
| Lambda timeout (60s) | ONTAP management endpoint unreachable | Check Security Group rules (TCP 443 outbound), verify ONTAP management LIF is up |
| HTTP 401 from ONTAP | Credentials expired or incorrect | Check Secrets Manager secret value, verify fsxadmin password |
| HTTP 403 from ONTAP | Insufficient permissions | Verify fsxadmin role has required API access (default: full) |
| `SVM not found` error | SVM name mismatch | Verify SVM name matches exactly (case-sensitive). Use `vserver show` to list |
| `Volume not found` error | Volume doesn't exist or wrong SVM | Verify volume name and SVM association |
| DLQ messages accumulating | Repeated failures | Check Lambda CloudWatch Logs for the root cause, then replay from DLQ |

### Block Not Taking Effect

| Symptom | Cause | Solution |
|---------|-------|----------|
| SMB user still has access after block | Existing session active | Use `contain_smb_threat` (includes session disconnect) or wait for session timeout |
| NFS client still has access | NFS attribute cache | Wait 60s (default `actimeo`) or remount with `mount -o actimeo=0` for testing |
| Block exists but ONTAP shows no entry | Wrong SVM | Verify the SVM name in your SNS message matches the target SVM |

### TTL Auto-Unblock Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Blocks not being removed | EventBridge Scheduler not running | Check scheduler state in EventBridge console |
| All blocks removed too early | TTL Lambda removes ALL response-marker blocks | See "TTL Limitation" note below |
| Cleanup Lambda errors | ONTAP unreachable from TTL Lambda | Same VPC/SG requirements as main Lambda |

> **TTL Limitation**: The current TTL implementation removes ALL blocks with the `fsxn_auto_response` marker on each run, regardless of when they were created. ONTAP name-mapping entries do not carry creation timestamps. For time-accurate TTL enforcement, implement a DynamoDB tracking table that records block creation time and have the TTL Lambda check that table before removal. This is tracked as a future enhancement.

### Common `aws sns publish` Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `AuthorizationError` | IAM user lacks `sns:Publish` permission | Add `sns:Publish` permission for the trigger topic ARN |
| `InvalidParameter` | Malformed JSON in message | Validate JSON with `echo '<msg>' | python3 -m json.tool` |
| `TopicNotFound` | Wrong topic ARN | Verify ARN from CloudFormation stack outputs |

---

## FAQ

**Q: Does this replace DII Storage Workload Security entirely?**
A: It provides the same *containment actions* (block/snapshot/disconnect). Detection intelligence differs: DII uses built-in per-user ML baselines, while this approach uses your chosen SIEM's analytics capabilities. For organizations with existing SIEM investments, the combined approach can provide broader context (network + application + storage) than storage-only detection.

**Q: What happens if the Lambda cannot reach ONTAP?**
A: The invocation fails, the message goes to the DLQ, and the DLQ alarm fires. Investigate network connectivity (Security Group, route tables, ONTAP management LIF status).

**Q: Can I block a user across multiple SVMs simultaneously?**
A: Send one SNS message per SVM. The composite actions operate on a single SVM per invocation. For multi-SVM blocking, publish multiple messages or implement a fan-out Lambda.

**Q: How quickly does the block take effect?**
A: SMB name-mapping blocks are effective immediately for new connections. Existing sessions remain active until disconnected (the `contain_smb_threat` action handles this). NFS export-policy rules are effective immediately for new mounts; existing mounts may require cache expiry.

**Q: Is there a risk of blocking legitimate users?**
A: Yes — this is true for any automated response system. Mitigations: (1) set detection thresholds conservatively, (2) use the notification topic to alert operators immediately, (3) implement time-limited blocks with auto-unblock, (4) maintain a runbook for rapid manual reversal.
