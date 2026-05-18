# Event Sources Guide

## Overview

This project supports **three event sources** from FSx for ONTAP.

```
┌─────────────────────────────────────────────────────────────────────┐
│ FSx for ONTAP Event Sources                                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Audit Logs (File Access Auditing)                               │
│     → S3 Bucket → EventBridge → Lambda → Vendor                    │
│                                                                     │
│  2. EMS (Event Management System)                                   │
│     → Webhook → API Gateway → Lambda → Vendor                      │
│     → CloudWatch Events → EventBridge → Lambda → Vendor            │
│                                                                     │
│  3. FPolicy (File Screening)                                        │
│     → TCP:9898 → ECS Fargate → SQS → EventBridge → Lambda → Vendor│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Audit Logs (File Access Auditing)

### Target Events
- File/directory access (EventID 4663)
- Object open (EventID 4656)
- Security descriptor changes (EventID 4670)
- CIFS logon/logoff

### Delivery Path
```
FSx ONTAP (vserver audit) → S3 Bucket → EventBridge → Lambda → Vendor API
```

### Configuration
See Step 2 in the [Prerequisites Guide](prerequisites.md).

---

## 2. EMS (Event Management System)

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

FSx ONTAP publishes EMS events as CloudWatch Events.

```
FSx ONTAP EMS → CloudWatch Events → EventBridge Rule → Lambda → Vendor API
```

**EventBridge Rule Example:**
```json
{
  "source": ["aws.fsx"],
  "detail-type": ["FSx ONTAP EMS Event"],
  "detail": {
    "event-name": ["arw.volume.state", "wafl.quota.softlimit.exceeded"]
  }
}
```

References: [AWS Docs - Monitoring FSx ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring_overview.html) | [EMS alerts for ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/EMS-ARP.html)

---

## 3. FPolicy (File Screening)

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
│ FSx ONTAP    │ ─────────────────→ │ ECS Fargate      │
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
| Compliance audit | Audit Logs | S3 → EventBridge → Lambda |
| Ransomware detection alert | EMS (ARP/AI) | Webhook → API GW → Lambda |
| Capacity management alert | EMS (Quota) | CloudWatch → EventBridge → Lambda |
| Real-time file monitoring | FPolicy | TCP:9898 → ECS Fargate → SQS → EventBridge → Lambda |
| DLP (Data Loss Prevention) | FPolicy (sync) | TCP:9898 → ECS Fargate → Decision |
| Security SIEM integration | Audit Logs + EMS | Combined pattern |
