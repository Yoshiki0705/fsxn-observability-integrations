# Security Monitoring & Incident Response — Document Navigation Index

🌐 [日本語](../ja/security-monitoring-index.md) | **English** (this page)

## Overview

This index provides navigation across all security-related documentation in this project. Use it to find the right document for your role and task.

---

## By Role

### Storage Administrator
| Need | Document | Key Section |
|------|----------|-------------|
| Understand what EMS events are available | [EMS Detection Capabilities](ems-detection-capabilities.md) | Event Catalog |
| Configure EMS webhook destinations | [EMS Detection Capabilities](ems-detection-capabilities.md) | ONTAP Filter Configuration Guide |
| Handle ARP detection alerts | [ARP Incident Response Guide](arp-incident-response-guide.md) | Step-by-step response |
| Check active user/IP blocks | [Automated Response Guide](automated-response-guide.md) | Operational Procedures |
| Set up syslog to CloudWatch | [Syslog VPCE Setup Guide](syslog-vpce-setup-guide.md) | Full setup |

### Security Analyst / SOC
| Need | Document | Key Section |
|------|----------|-------------|
| Understand automated storage-layer blocking | [Automated Response Guide](automated-response-guide.md) | How Blocking Works |
| Run the full demo for evaluation | [Demo Runbook](demo-automated-response.md) | All phases |
| Understand this repo's coverage across all six NIST CSF 2.0 functions, not just containment | [Cyber Resilience Capability Map](cyber-resilience-capability-map.md) | NIST CSF 2.0 Overview |
| Build a user/IP/file-path forensic investigation dashboard (who accessed what, from where) | [Cyber Resilience Capability Map](cyber-resilience-capability-map.md) | Respond (RS) |
| Verify a snapshot is clean before relying on it as a recovery point (RC.RP) | [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) | How Verification Works |
| Discover PII in file contents, not just field-level classification | [Content-Level PII Classification Scanner](content-classification-scanner.md) | How Classification Works |
| Compare with dedicated security products (e.g., DII Storage Workload Security) | [Automated Response Guide](automated-response-guide.md) | Comparison table, FAQ |
| Review detection latency | [EMS Detection Capabilities](ems-detection-capabilities.md) | Delivery Latency Comparison |

### Cloud Architect / DevOps
| Need | Document | Key Section |
|------|----------|-------------|
| Deploy automated response | [Automated Response Guide](automated-response-guide.md) | Deployment |
| Deploy CloudWatch Log Alarms | [CloudWatch Log Alarm guide](cloudwatch-log-alarm.md) | Deploy |
| Understand architecture evolution | [Architecture Evolution: Syslog VPCE](architecture-evolution-syslog-vpce.md) | Before/After |
| Multi-account deployment | [Multi-Account Deployment](multi-account-deployment.md) | StackSets |

### Compliance / Audit
| Need | Document | Key Section |
|------|----------|-------------|
| Evidence pack template | [Compliance Evidence Pack](compliance-evidence-pack.md) | All |
| Data classification (field-level) | [Data Classification](data-classification.md) | PII fields |
| Data classification (file-content-level) | [Content-Level PII Classification Scanner](content-classification-scanner.md) | How Classification Works |
| Evidence a recovery point was tested clean (RC.RP) | [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) | Testing, Deployment |
| Log retention policies | [Pipeline SLO](pipeline-slo.md) | Retention |
| Audit trail for blocks | [Automated Response Guide](automated-response-guide.md) | Security Considerations |

---

## By Feature

### Detection → Response Pipeline

```
[1] Configure Detection
    └─→ EMS Detection Capabilities (ems-detection-capabilities.md)
    └─→ CloudWatch Log Alarm (cloudwatch-log-alarm.md)
    └─→ FPolicy Setup (vendor docs)

[2] Deploy Response
    └─→ Automated Response Guide (automated-response-guide.md)
    └─→ CLI Helper (shared/scripts/automated-response-cli.sh)

[3] Incident Handling
    └─→ ARP Incident Response Guide (arp-incident-response-guide.md)
    └─→ Demo Runbook (demo-automated-response.md)
    └─→ Runbooks (runbooks/)

[3.5] Forensic Investigation (cross-cutting, any phase)
    └─→ Cyber Resilience Capability Map (cyber-resilience-capability-map.md)
    └─→ Splunk / Datadog / Grafana / Elastic dashboards (per-vendor guidance under Respond)

[3.6] Recovery Verification & Data Discovery (Recover / Identify functions)
    └─→ Verified-Clean Recovery Point Guide (verified-recovery-point-guide.md)
    └─→ Content-Level PII Classification Scanner (content-classification-scanner.md)

[4] Operations
    └─→ PagerDuty Escalation (pagerduty-escalation-guide.md)
    └─→ Pipeline SLO (pipeline-slo.md)
    └─→ TTL Auto-Unblock (automated-response-guide.md #time-limited)
```

### Document Dependency Graph

```
architecture-evolution-syslog-vpce.md
  ├─→ ems-detection-capabilities.md (EMS events via syslog)
  ├─→ cloudwatch-log-alarm.md (alerting on those logs)
  │     └─→ automated-response-guide.md (acting on those alerts)
  │           ├─→ demo-automated-response.md (step-by-step proof)
  │           └─→ arp-incident-response-guide.md (ARP-specific flow)
  └─→ demo-scenarios.md (Scenarios 7-10)
```

---

## Quick Reference: Key Commands

### EMS Monitoring
```bash
# Check EMS webhook delivery
aws logs filter-log-events --log-group-name /aws/lambda/fsxn-*-ems-* --filter-pattern "arw"

# Check syslog delivery
aws logs filter-log-events --log-group-name /syslog/fsxn-admin-audit --limit 5
```

### Automated Response
```bash
# Block user
./shared/scripts/automated-response-cli.sh contain-smb --domain CORP --user jdoe --volume vol1 --reason "reason"

# Check active blocks
ssh fsxadmin@<mgmt-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
ssh fsxadmin@<mgmt-ip> "export-policy rule show -clientmatch *fsxn_auto_response*"

# Unblock
./shared/scripts/automated-response-cli.sh unblock-smb --domain CORP --user jdoe
```

### CloudWatch Log Alarm
```bash
# Deploy detection alarm
DETECTION_TYPE=sensitive-file-access bash shared/scripts/deploy-log-alarm.sh

# Check alarm state
aws cloudwatch describe-alarms --alarm-name-prefix "fsxn-" --query 'MetricAlarms[].{Name:AlarmName,State:StateValue}'
```

---

## Related Blog Posts

| Part | Topic | Documents |
|------|-------|-----------|
| 2 | ARP + FPolicy Detection | `arp-incident-response-guide.md` |
| 14 | Syslog VPCE Setup | `architecture-evolution-syslog-vpce.md`, `syslog-vpce-setup-guide.md` |
| 17 | CloudWatch Log Alarm | `cloudwatch-log-alarm.md` |
| 18 | Automated Incident Response | `automated-response-guide.md`, `demo-automated-response.md` |
