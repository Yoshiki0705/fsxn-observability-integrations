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
│     → External Engine → API Gateway → Lambda → Vendor              │
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
| **HA** | `cf.fsm.takeoverStarted` | HA takeover started | Availability |
| **Network** | `net.linkDown` | Network link down | Availability |

### Delivery Paths

#### Pattern A: EMS Webhook → API Gateway → Lambda (Recommended)

ONTAP 9.10.1+ supports EMS event forwarding via Webhook.

```
ONTAP EMS → Webhook (HTTPS) → API Gateway → Lambda → Vendor API
```

#### Pattern B: CloudWatch → EventBridge → Lambda

FSx ONTAP publishes EMS events as CloudWatch Events.

```
FSx ONTAP EMS → CloudWatch Events → EventBridge Rule → Lambda → Vendor API
```

References: [AWS Docs - Monitoring FSx ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring_overview.html) | [EMS alerts for ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/EMS-ARP.html)

---

## 3. FPolicy (File Screening)

### Target Events

| Protocol | Supported Operations |
|----------|---------------------|
| **CIFS/SMB** | create, open, close, read, write, rename, delete, setattr, getattr |
| **NFSv3** | create, mkdir, read, write, rename, unlink, rmdir, setattr, link, symlink |
| **NFSv4** | create, open, close, read, write, rename, remove, setattr, getattr |

### Delivery Path
```
File Operation → FPolicy Engine → External Server (API Gateway) → Lambda → Vendor API
```

### Notes
- FPolicy External Engine requires TCP (API Gateway + NLB configuration)
- Asynchronous mode recommended (minimizes performance impact)
- Synchronous mode can block file operations (for DLP use cases)

References: [NetApp FPolicy API](https://library.netapp.com/ecmdocs/ECMLP2886776/html/resources/fpolicy_event.html) | [ONTAP EMS Webhook](https://docs.netapp.com/us-en/ontap/error-messages/configure-webhooks-event-notifications-task.html)

---

## Use Case Recommendations

| Use Case | Event Source | Recommended Pattern |
|----------|-------------|-------------------|
| Compliance audit | Audit Logs | S3 → EventBridge → Lambda |
| Ransomware detection alert | EMS (ARP/AI) | Webhook → API GW → Lambda |
| Capacity management alert | EMS (Quota) | CloudWatch → EventBridge → Lambda |
| Real-time file monitoring | FPolicy | External Engine → API GW → Lambda |
| DLP (Data Loss Prevention) | FPolicy (sync) | External Engine → Lambda → Decision |
| Security SIEM integration | Audit Logs + EMS | Combined pattern |
