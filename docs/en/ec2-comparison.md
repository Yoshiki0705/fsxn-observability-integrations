# Comparison: EC2-Based Pattern vs Serverless Pattern

## Overview

This document compares two architecture patterns for delivering FSx for NetApp ONTAP audit logs to Splunk.

- **EC2-Based Pattern**: syslog-ng + Splunk Universal Forwarder on an EC2 instance
- **Serverless Pattern**: S3 Access Point + EventBridge + Lambda + Secrets Manager

The EC2-based pattern is the architecture introduced in the official AWS blog:
https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/

## Architecture Diagrams

### EC2-Based Pattern

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  FSx for ONTAP  │────▶│  EC2 Instance    │────▶│  Splunk Cloud   │
│  (Audit Logs)   │     │  (t3.medium)     │     │  (HEC Endpoint) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │    │
                               │    │
                        ┌──────┘    └──────┐
                        ▼                  ▼
               ┌──────────────┐   ┌──────────────────┐
               │   syslog-ng  │   │  Splunk Universal │
               │  (Log Ingest)│   │  Forwarder (Ship) │
               └──────────────┘   └──────────────────┘
```

**Components:**
- EC2 Instance (t3.medium): Hosts syslog-ng and Universal Forwarder
- syslog-ng: Receives and parses syslog messages from FSx ONTAP
- Splunk Universal Forwarder: Forwards parsed logs to Splunk Cloud/Enterprise

### Serverless Pattern

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  FSx for ONTAP  │────▶│  FSx ONTAP       │────▶│  EventBridge    │
│  (Audit Logs)   │     │  S3 Access Point │     │  Scheduler      │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Splunk Cloud   │◀────│     Lambda       │◀────│  Secrets Manager│
│  (HEC Endpoint) │     │  (Transform/Ship)│     │  (HEC Token)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Components:**
- S3 Access Point: S3 API access layer for FSx ONTAP audit logs
- EventBridge Scheduler: Invokes Lambda periodically (every 5 minutes)
- Lambda: Retrieves, parses, and ships logs to Splunk HEC
- Secrets Manager: Secure management of HEC token

## Comparison Table

| Dimension | EC2-Based Pattern | Serverless Pattern |
|-----------|-------------------|-------------------|
| **Monthly Cost (1GB/day)** | ~$50–70/month | ~$5–15/month |
| **Operational Overhead** | High (3 components to manage) | Low (managed services) |
| **Scaling** | Manual (instance resize) | Automatic (Lambda concurrency) |
| **Log Delivery Latency** | Seconds to tens of seconds | Minutes (Scheduler interval) |
| **High Availability** | Manual setup (Multi-AZ, ASG) | Built-in (Lambda HA) |
| **Patch Management** | User responsibility (OS, syslog-ng, UF) | AWS responsibility (Lambda runtime) |

## Cost Breakdown (1GB/day, ap-northeast-1)

### EC2-Based Pattern: ~$50–70/month

| AWS Service | Monthly Cost (USD) | Notes |
|-------------|-------------------|-------|
| EC2 (t3.medium) | ~$40 | On-demand, 24/7 |
| EBS (gp3, 30GB) | ~$5 | OS + log buffer |
| Data Transfer (outbound) | ~$5–10 | Transfer to Splunk Cloud |
| Splunk Universal Forwarder | $0 | Free license |
| CloudWatch (basic monitoring) | ~$0–5 | Metrics + logs |
| **Total** | **~$50–70** | |

### Serverless Pattern: ~$5–15/month

| AWS Service | Monthly Cost (USD) | Notes |
|-------------|-------------------|-------|
| Lambda | ~$1–3 | 5-min interval, 256MB, ~30s/invocation |
| S3 Requests | ~$1 | ListObjects + GetObject |
| EventBridge Scheduler | ~$1 | Periodic schedule |
| Secrets Manager | ~$1 | 1 secret + API calls |
| CloudWatch (logs + metrics) | ~$1–5 | Lambda logs + alarms |
| Data Transfer (outbound) | ~$0–5 | Transfer to Splunk Cloud |
| **Total** | **~$5–15** | |

## Detailed Comparison

### Operational Overhead

| Item | EC2-Based | Serverless |
|------|-----------|------------|
| Managed infrastructure components | 3 (EC2, syslog-ng, UF) | 0 (all managed) |
| OS patching | Monthly (user responsibility) | Not required |
| Log rotation configuration | Required (logrotate) | Not required |
| Security group management | Required | Lambda only |
| SSH key management | Required | Not required |
| Disk capacity monitoring | Required | Not required |

### Scaling Behavior

| Item | EC2-Based | Serverless |
|------|-----------|------------|
| Maximum throughput | Instance size dependent | Lambda concurrency (default 1000) |
| Scale-up method | Instance type change (downtime) | Automatic (no config change) |
| Scale-down | Manual | Automatic (pay-per-use) |
| Burst handling | Limited | Lambda concurrency |

### Log Delivery Latency

| Item | EC2-Based | Serverless |
|------|-----------|------------|
| Log generation → collection | Seconds (syslog real-time) | Minutes (Scheduler interval) |
| Collection → Splunk arrival | Seconds (UF real-time forwarding) | Seconds (Lambda → HEC) |
| End-to-end | ~10–30 seconds | ~5–10 minutes |

### High Availability (HA)

| Item | EC2-Based | Serverless |
|------|-----------|------------|
| Failover mechanism | Auto Scaling Group + ALB | Lambda built-in HA |
| Recovery time | Minutes (new instance launch) | Immediate (auto-execute in another AZ) |
| Data loss risk | Buffer logs lost on EBS failure | Events retained in DLQ |
| Additional cost | 2x for Multi-AZ | No additional cost |

### Patch Management

| Item | EC2-Based | Serverless |
|------|-----------|------------|
| Responsible party | User | AWS (Lambda runtime) |
| Scope | OS, syslog-ng, UF, Python, etc. | None (no user management) |
| Update frequency | Monthly recommended | AWS auto-applies |
| Downtime | During patch application | None |

## Recommendation Guide

| Scenario | Recommended Pattern | Rationale |
|----------|-------------------|-----------|
| **Low Volume (≤1GB/day)** | Serverless | Significantly more cost-effective ($5–15 vs $50–70). Minimal operational burden |
| **High Volume (>10GB/day)** | EC2-Based (existing infra) / Firehose (new) | Suitable for real-time processing of large log volumes. Use EC2 pattern with existing infrastructure; use Firehose pattern for greenfield deployments |
| **Minimal Ops** | Serverless | Patch management, scaling, and HA are all automatic. Zero infrastructure management |

## Summary

- **Cost**: Serverless pattern costs approximately 1/5 to 1/10 of the EC2-based pattern
- **Operations**: Serverless pattern requires no infrastructure management, significantly reducing operational burden
- **Latency**: EC2-based pattern enables near real-time delivery (tens of seconds). Serverless has a delay of several minutes
- **Scaling**: Serverless scales automatically. EC2 requires manual intervention
- **Recommendation**: For the majority of use cases (especially ≤1GB/day), the serverless pattern is recommended

> **Note**: If strict latency requirements exist (delivery within 10 seconds is mandatory), consider the EC2-based pattern or the EMS Webhook path.
