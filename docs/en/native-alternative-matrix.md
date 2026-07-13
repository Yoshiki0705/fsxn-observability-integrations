# AWS-Native Alternative Matrix — System Manager / Workload Factory / DII

🌐 [日本語](../ja/native-alternative-matrix.md) | **English** (this page)

## Purpose

This document maps every major feature of ONTAP System Manager, NetApp Workload Factory, and DII Storage Workload Security to its AWS-native equivalent implementation in this repository. The goal: demonstrate that production-grade FSx for ONTAP operations, monitoring, and security can be achieved without proprietary management consoles.

> **Positioning note**: This is not a "competitor comparison." Each tool serves different contexts. This matrix helps teams that have already chosen AWS-native operations to verify full feature coverage, and helps teams evaluating options to understand what's available without additional licensing.

---

## ONTAP System Manager — Feature Coverage

| System Manager Feature | AWS-Native Equivalent | This Repo | Status |
|----------------------|----------------------|-----------|:------:|
| **Performance: IOPS** | CloudWatch `DataReadOperations` + `DataWriteOperations` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **Performance: Throughput** | CloudWatch `DataReadBytes` + `DataWriteBytes` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **Performance: Latency** | CloudWatch `DataReadLatency` + `DataWriteLatency` (detailed metrics) | `fsxn-monitoring-dashboard.yaml` | ⚠️ Requires detailed metrics enablement |
| **Performance: Network Utilization** | CloudWatch `NetworkThroughputUtilization` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **Capacity: Storage Used** | CloudWatch `StorageUsed` + `StorageCapacityUtilization` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **Capacity: Alerts** | CloudWatch Alarm on `StorageCapacityUtilization` | `fsxn-monitoring-dashboard.yaml` (threshold alarm) | ✅ |
| **Qtree: Quota Management** | ONTAP REST API `/storage/quota/rules` | CLI scripts / manual | ⚠️ Management via API, no GUI |
| **Qtree: Quota Monitoring** | Lambda → ONTAP REST API → CloudWatch Custom Metric | `qtree-quota-monitor.yaml` | ✅ |
| **Qtree: Quota Alerts** | CloudWatch Alarm on `QtreeQuotaUsedPercent` | `qtree-quota-monitor.yaml` | ✅ |
| **Volume: Create/Delete/Resize** | FSx Console + ONTAP REST API | CloudFormation templates + scripts | ✅ |
| **Snapshot: Create/Schedule** | FSx Backup + ONTAP REST API | `ontap_response.py` + FSx native | ✅ |
| **Snapshot: Restore** | FSx Console + ONTAP REST API | `restore-verification.yaml` (verify before restore) | ✅ |
| **NFS Export Management** | ONTAP REST API | `ontap_response.py` (export-policy rules) | ✅ |
| **SMB Share Management** | ONTAP REST API | `ontap_response.py` (name-mapping) | ✅ |
| **EMS Event Viewer** | CloudWatch Logs (syslog VPC EP) | `syslog-vpce-cloudwatch.yaml` | ✅ |
| **ARP Status** | EMS → Observability pipeline | 9 vendor integrations + EMS webhook | ✅ |
| **SnapMirror Management** | FSx Console + ONTAP REST API | Docs (manual procedure) | ⚠️ No automation |
| **QoS Policy** | ONTAP REST API | — | ❌ Out of scope |
| **Network (LIF/DNS)** | FSx Console + ONTAP REST API | — | ❌ Infrastructure management |
| **FPolicy Configuration** | ONTAP REST API | FPolicy server (Fargate) + scripts | ✅ |
| **Audit Configuration** | ONTAP CLI/REST API | Setup scripts + docs | ✅ |

---

## Workload Factory — Feature Coverage

| Workload Factory Feature | AWS-Native Equivalent | This Repo | Status |
|-------------------------|----------------------|-----------|:------:|
| **File System Creation Wizard** | FSx Console / CloudFormation | `demo-ad-environment.yaml` + templates | ✅ |
| **Cost Optimization Recommendations** | AWS Cost Explorer + CloudWatch metrics | — | ❌ Future |
| **FabricPool Tiering Recommendations** | CloudWatch capacity metrics + ONTAP tiering API | Docs (manual guidance) | ⚠️ |
| **Backup Management** | FSx Backup (AWS managed) | AWS native (no template needed) | ✅ |
| **Replication Configuration** | FSx Console + SnapMirror API | Docs (manual procedure) | ⚠️ |
| **Security Posture Scan** | AWS Security Hub + cfn-guard | `guard/rules/` + CI | ✅ |
| **GenAI Data Preparation** | Bedrock Knowledge Bases + S3 AP | S3AP Patterns repo | ✅ |
| **Data Migration** | AWS DataSync | — | ❌ Out of scope |
| **Compliance Templates** | CloudFormation + cfn-guard | `compliance-evidence-pack.md` | ✅ |

---

## DII Storage Workload Security — Feature Coverage

| DII Feature | AWS-Native Equivalent | This Repo | Status |
|------------|----------------------|-----------|:------:|
| **ML-Based Anomaly Detection** | ONTAP ARP/AI (built-in) + SIEM ML | EMS → Datadog/9 vendors | ✅ |
| **User Auto-Block** | ONTAP REST API (name-mapping deny) | `ontap_response.py` + `automated-response.yaml` | ✅ E2E verified |
| **IP Auto-Block** | ONTAP REST API (export-policy) + VPC NACL | `ontap_response.py` + `automated-response.yaml` | ✅ E2E verified |
| **Protective Snapshot** | ONTAP REST API | `ontap_response.py` `create_snapshot` | ✅ E2E verified |
| **Session Disconnect** | ONTAP REST API (CIFS sessions) | `ontap_response.py` `disconnect_smb_sessions` | ✅ E2E verified |
| **Forensics Dashboard** | Datadog custom dashboard | `datadog-forensics-dashboard.png` | ✅ Created |
| **User Activity Timeline** | Datadog Timeseries widget | Forensics dashboard | ✅ |
| **File Access Audit Trail** | Audit logs → Datadog Log Explorer | Pipeline + Forensics dashboard | ✅ |
| **Affected Volume Visualization** | Datadog TopList widget | Forensics dashboard | ✅ |
| **Alert Severity Distribution** | Datadog widgets | Forensics dashboard | ✅ |
| **Recovery Point Verification** | Step Functions (FlexClone + S3 AP + Scan) | `restore-verification.yaml` | ✅ E2E verified |
| **Auto-Unblock (TTL)** | EventBridge Scheduler | `automated-response-ttl.yaml` | ✅ |
| **Multi-SVM Containment** | Step Functions fan-out / multi-SVM CLI | `automated-response-multi-svm-cli.sh` | ✅ |

---

## Summary: Coverage Status

| Product | Features Mapped | ✅ Covered | ⚠️ Partial | ❌ Out of Scope |
|---------|:--------------:|:----------:|:----------:|:--------------:|
| System Manager | 18 | 14 | 2 | 2 |
| Workload Factory | 9 | 5 | 2 | 2 |
| DII SWS | 13 | 13 | 0 | 0 |

**Key insight**: Security/incident-response features (DII equivalent) are **100% covered**. Operations monitoring (System Manager equivalent) is **78% covered** — remaining gaps are QoS management and SnapMirror automation, which are infrastructure-management tasks better suited to the FSx Console or a dedicated IaC tool.

---

## Deployment Quick Reference

| Capability | Template | Deploy Order |
|-----------|----------|:------------:|
| Performance & Capacity | `fsxn-monitoring-dashboard.yaml` | Any time |
| Qtree Quota Monitoring | `qtree-quota-monitor.yaml` | After VPC EP exists |
| Incident Response | `automated-response.yaml` | Tier 2 |
| Recovery Verification | `restore-verification.yaml` | After Tier 2 |
| Forensics | Datadog API (dashboard JSON) | After log pipeline |

---

## Related Documents

- [Deployment Guide](deployment-guide.md) — Full stack deployment paths and VPC Endpoint management
- [Cyber Resilience Capability Map](cyber-resilience-capability-map.md) — NIST CSF 2.0 mapping
- [Automated Response Guide](automated-response-guide.md) — DII-equivalent containment actions
- [Verified Recovery Point Guide](verified-recovery-point-guide.md) — Step Functions verification workflow
