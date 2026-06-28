# Event Sources Guide

## Overview

This project supports **four event sources** from FSx for ONTAP.

```
┌─────────────────────────────────────────────────────────────────────┐
│ FSx for ONTAP Event Sources                                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. File Access Audit Logs                                          │
│     → S3 Bucket → EventBridge → Lambda → Vendor                    │
│                                                                     │
│  2. Admin Audit Logs (NEW — Syslog VPCE)                            │
│     → Syslog → VPC Endpoint → CloudWatch Logs                      │
│     (No EC2/Lambda required for AWS-native path)                    │
│                                                                     │
│  3. EMS (Event Management System)                                   │
│     → Webhook → API Gateway → Lambda → Vendor                      │
│     → CloudWatch Events → EventBridge → Lambda → Vendor            │
│                                                                     │
│  4. FPolicy (File Screening)                                        │
│     → TCP:9898 → ECS Fargate → SQS → EventBridge → Lambda → Vendor│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. File Access Audit Logs

### Target Events
- File/directory access (EventID 4663)
- Object open (EventID 4656)
- Security descriptor changes (EventID 4670)
- CIFS logon/logoff

### Delivery Path
```
FSx for ONTAP (vserver audit) → S3 Bucket → EventBridge → Lambda → Vendor API
```

### Configuration
See Step 2 in the [Prerequisites Guide](prerequisites.md).

---

## 2. Admin Audit Logs (Management Activity — Syslog VPCE)

### Target Events
- ONTAP CLI command execution (SSH sessions)
- REST API calls (POST/GET/PATCH/DELETE)
- Privilege escalation (`set -privilege diagnostic`)
- Login/logout events
- Configuration changes (volume create, policy modify, etc.)

### Delivery Path (AWS-Native — No EC2 Required)

```
FSx for ONTAP (cluster log-forwarding)
    │ Syslog (TCP port 1514 or 6514)
    ▼
VPC Endpoint (com.amazonaws.{region}.syslog-logs)
    │ AWS PrivateLink
    ▼
CloudWatch Logs (/syslog/fsxn-admin-audit)
```

This path is fully managed — no Lambda, no EC2, no agents. CloudWatch Logs automatically parses syslog fields (facility, severity, hostname, appName, message).

### Key Advantages Over EC2 Syslog

| Aspect | EC2 syslog-ng (legacy) | Syslog VPC Endpoint (new) |
|--------|----------------------|--------------------------|
| Compute | EC2 instance(s) | None (managed service) |
| Cost | ~$66/month (EC2+EBS) | ~$8/month (VPCE + CW Logs) |
| Patching | Monthly OS updates | None |
| HA | Manual multi-AZ setup | Multi-AZ ENIs built-in |
| Deploy time | Hours | 15 minutes |

### Configuration

**CloudFormation**: `shared/templates/syslog-vpce-cloudwatch.yaml`

**ONTAP REST API**:
```bash
curl -sk -u fsxadmin:<password> \
  -X POST "https://<mgmt-ip>/api/security/audit/destinations?force=true" \
  -H "Content-Type: application/json" \
  -d '{"address":"<VPCE_ENI_IP>","port":1514,"protocol":"tcp_unencrypted","facility":"local7"}'
```

**Protocol options**:

| Protocol | Port | ONTAP parameter | When to use |
|----------|------|-----------------|-------------|
| TCP+TLS | 6514 | `tcp_encrypted` | Production (encrypted) |
| TCP plaintext | 1514 | `tcp_unencrypted` | Initial validation, PrivateLink-only networks |

### Optional: Fan-out to Vendors

```
CloudWatch Logs → Subscription Filter → Lambda → Datadog/Splunk/SIEM
CloudWatch Logs → Subscription Filter → Firehose → Splunk/S3
```

### Setup Guide

See [Syslog VPCE Setup Guide](syslog-vpce-setup-guide.md) for full step-by-step instructions.

References: [AWS Docs - Syslog ingestion](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_Syslog.html) | [NetApp - Audit destinations](https://docs.netapp.com/us-en/ontap/system-admin/forward-command-history-log-file-destination-task.html)

---

## 3. EMS (Event Management System)

### Target Events

| Category | EMS Event Name | Description | Use Case |
|----------|---------------|-------------|----------|
| **ARP/AI** | `arw.volume.state` | Ransomware detection/state change | Security alert |
| **ARP/AI** | `arw.vserver.state` | ARP SVM-level state change | Security alert |
| **Quota** | `wafl.quota.softlimit.exceeded` | Soft quota threshold exceeded | Capacity mgmt |
| **Quota** | `wafl.quota.hardlimit.exceeded` | Hard quota threshold exceeded | Capacity mgmt |
| **Capacity** | `sms.vol.full` | Volume full | Capacity mgmt |
| **Capacity** | `sms.vol.nearlyFull` | Volume nearly full (95%) | Capacity mgmt |
| **Performance** | `qos.monitor.memory.maxed` | QoS memory limit reached | Performance |
| **HA** | `cf.fsm.takeoverStarted` | HA takeover started | Availability |
| **Network** | `net.linkDown` | Network link down | Availability |

### Delivery Paths

#### Pattern A: EMS Webhook → API Gateway → Lambda (Recommended)

ONTAP 9.10.1+ supports EMS event forwarding via Webhook.

```
ONTAP EMS → Webhook (HTTPS) → API Gateway → Lambda → Vendor API
```

**ONTAP CLI Configuration:**
```bash
# 1. Create Webhook notification destination
event notification destination create -name aws-apigw \
  -syslog-transport https \
  -syslog-port 443 \
  -url https://<api-gateway-id>.execute-api.ap-northeast-1.amazonaws.com/prod/ems

# 2. Create event filter
event filter create -filter-name arp-and-quota
event filter rule add -filter-name arp-and-quota -type include \
  -message-name arw.volume.state
event filter rule add -filter-name arp-and-quota -type include \
  -message-name wafl.quota.*

# 3. Create notification
event notification create -filter-name arp-and-quota \
  -destinations aws-apigw
```

#### Pattern B: CloudWatch → EventBridge → Lambda

FSx for ONTAP publishes EMS events as CloudWatch Events.

```
FSx for ONTAP EMS → CloudWatch Events → EventBridge Rule → Lambda → Vendor API
```

**EventBridge Rule Example:**
```json
{
  "source": ["aws.fsx"],
  "detail-type": ["FSx for ONTAP EMS Event"],
  "detail": {
    "event-name": ["arw.volume.state", "wafl.quota.softlimit.exceeded"]
  }
}
```

References: [AWS Docs - Monitoring FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring_overview.html) | [EMS alerts for ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/EMS-ARP.html)

---

## 4. FPolicy (File Screening)

### Target Events

FPolicy monitors file operations via event-driven TCP notifications and notifies an external engine.

| Protocol | Supported Operations |
|----------|---------------------|
| **CIFS/SMB** | create, open, close, read, write, rename, delete, setattr, getattr |
| **NFSv3** | create, mkdir, read, write, rename, unlink, rmdir, setattr, link, symlink |
| **NFSv4** | create, open, close, read, write, rename, remove, setattr, getattr |

### Architecture

FPolicy uses a proprietary binary protocol over TCP, so HTTP/API Gateway cannot receive it directly.
A custom FPolicy server container handles the TCP protocol translation and delivers events via SQS → EventBridge.

```
┌──────────────┐     TCP:9898      ┌──────────────────┐
│ FSx for ONTAP    │ ─────────────────→ │ ECS Fargate      │
│ FPolicy      │  (direct connect) │ FPolicy Server   │
└──────────────┘                    └────────┬─────────┘
                                             │ SQS SendMessage
                                             ▼
                                    ┌──────────────────┐
                                    │ SQS Queue        │
                                    │ (FPolicy_Q)      │
                                    └────────┬─────────┘
                                             │ Event Source Mapping
                                             ▼
                                    ┌──────────────────┐
                                    │ Bridge Lambda    │
                                    │ (SQS→EventBridge)│
                                    └────────┬─────────┘
                                             │ PutEvents
                                             ▼
                                    ┌──────────────────┐
                                    │ EventBridge      │
                                    │ Custom Bus       │
                                    │ (fpolicy.fsxn)   │
                                    └────────┬─────────┘
                                             │ Rule
                                             ▼
                                    ┌──────────────────┐
                                    │ Vendor Lambda    │
                                    │ (forwarder)      │
                                    └──────────────────┘
```

### Delivery Path

```
File Operation → ONTAP FPolicy → TCP:9898 → ECS Fargate → SQS → EventBridge → Lambda → Vendor API
```

### Compute Mode Selection

| Mode | Characteristics | Recommended For |
|------|----------------|-----------------|
| **Fargate** | Serverless, includes IP Auto-Updater Lambda | Production (recommended) |
| **EC2** | Fixed IP, SSH access available | Debug/development |

> **Note**: In Fargate mode, the task IP changes on restart. The IP Auto-Updater Lambda
> detects ECS Task State Change events and automatically updates the FPolicy External Engine's
> `primary-servers` via the ONTAP REST API.

### FPolicy Configuration

```bash
# 1. Create FPolicy External Engine (port 9898, asynchronous mode)
vserver fpolicy policy external-engine create -vserver FPolicySMB \
  -engine-name fpolicy_lambda_engine \
  -primary-servers <fargate-task-ip> \
  -port 9898 \
  -extern-engine-type asynchronous

# 2. Create FPolicy Event
vserver fpolicy policy event create -vserver FPolicySMB \
  -event-name file-ops-event \
  -protocol cifs \
  -file-operations create,write,rename,delete

# 3. Create FPolicy Policy
vserver fpolicy policy create -vserver FPolicySMB \
  -policy-name file-screening \
  -events file-ops-event \
  -engine fpolicy_lambda_engine \
  -is-mandatory false

# 4. Enable FPolicy
vserver fpolicy enable -vserver FPolicySMB \
  -policy-name file-screening \
  -sequence-number 1
```

### Notes

- FPolicy uses a proprietary binary protocol over TCP — not HTTP/HTTPS
- ONTAP connects directly to the Fargate task IP (NLB is for health checks only)
- Asynchronous mode (`asynchronous`) recommended (minimizes performance impact)
- Synchronous mode (`synchronous`) can block file operations (for DLP use cases)
- NFSv3 write-complete has a 5-second default delay
- Container image is stored in ECR (ARM64 architecture)

### NLB Role

The NLB is NOT used for routing FPolicy traffic.
It is used only for ECS Fargate task health checks (TCP port 9898).
ONTAP connects directly to the Fargate task's ENI IP.

References: [NetApp FPolicy API](https://library.netapp.com/ecmdocs/ECMLP2886776/html/resources/fpolicy_event.html) | [FPolicy FAQ](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/FAQ:_FPolicy:_Auditing)

---

## Use Case Recommendations

| Use Case | Event Source | Recommended Pattern |
|----------|-------------|-------------------|
| Compliance audit (file access) | File Access Audit Logs | S3 → EventBridge → Lambda |
| Admin activity audit | Admin Audit Logs | Syslog VPCE → CloudWatch Logs |
| Ransomware detection alert | EMS (ARP/AI) | Webhook → API GW → Lambda |
| Capacity management alert | EMS (Quota) | CloudWatch → EventBridge → Lambda |
| Real-time file monitoring | FPolicy | TCP:9898 → ECS Fargate → SQS → EventBridge → Lambda |
| DLP (Data Loss Prevention) | FPolicy (sync) | TCP:9898 → ECS Fargate → Decision |
| Security SIEM integration | All sources | CloudWatch Logs hub → Subscription → SIEM |
