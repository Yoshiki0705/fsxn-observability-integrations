# File Access Audit Log — Format Comparison & Architecture Options

## Overview

This document clarifies the differences between FSx for ONTAP and FSx for Windows File Server regarding file access audit log format, CloudWatch Logs integration, and architecture options for large-volume log processing.

> **Common misconception**: "FSx for ONTAP can send file access audit logs directly to CloudWatch Logs in JSON format." This is incorrect — that capability exists only in FSx for Windows File Server, and even there the format is XML, not JSON.

---

## Format Comparison

| Attribute | FSx for ONTAP | FSx for Windows File Server |
|-----------|--------------|---------------------------|
| File access audit → CloudWatch Logs direct | **Not supported** | Supported (managed by AWS) |
| File access audit → Firehose direct | **Not supported** | Supported |
| Audit log format | **EVTX** (binary) or **XML** (ONTAP-specific) | **XML** (Windows Event Log XML) |
| Format configuration | `vserver audit create -format {evtx\|xml}` | Not configurable (always XML to CW Logs) |
| JSON output | **Not supported** | **Not supported** (XML in CW Logs) |
| Log storage location | ONTAP volume (file-based, rotated) | AWS-managed (direct to CW Logs/Firehose) |
| Access method | FSx for ONTAP S3 Access Point (S3 API) | AWS-managed delivery (no user action) |
| Admin audit → CloudWatch Logs | **Supported** (Syslog VPCE, June 2026) | N/A |

### Key Takeaway

Neither FSx for ONTAP nor FSx for Windows delivers file access audit logs in JSON to CloudWatch Logs. Both produce XML-format events. The difference is that FSx for Windows has a managed delivery path to CloudWatch Logs, while FSx for ONTAP requires an intermediary (Lambda, ECS, etc.) to read from the S3 Access Point.

---

## FSx for Windows File Server — How CloudWatch Logs Delivery Works

FSx for Windows sends audit events as XML text to CloudWatch Logs. Querying uses string matching, not structured JSON:

```
# CloudWatch Logs Insights query (text matching on XML)
fields @message
| filter @message like /4660/           # Delete events
| filter @message like /event.txt/      # Specific filename
```

The events arrive as XML in `@message`:
```xml
<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>
  <System>
    <EventID>4663</EventID>
    <TimeCreated SystemTime='2021-06-03T19:10:13.887Z'/>
    <Computer>amznfsxgyzohmw8.example.com</Computer>
  </System>
  <EventData>
    <Data Name='SubjectUserName'>Admin</Data>
    <Data Name='ObjectName'>\Device\HarddiskVolume8\share\event.txt</Data>
    <Data Name='AccessMask'>0x1</Data>
  </EventData>
</Event>
```

Reference: [AWS Docs — FSx for Windows File Access Auditing](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/file-access-auditing.html)

---

## FSx for ONTAP — What IS Supported for CloudWatch Logs

| Log Type | CloudWatch Logs Path | Format in CW Logs |
|----------|---------------------|-------------------|
| **Admin audit** (CLI/API ops) | Syslog VPCE → CW Logs (managed, no Lambda) | Syslog text (RFC 5424) |
| **File access audit** | **Not directly supported** — requires Lambda/ECS | N/A |
| **EMS events** | Syslog VPCE → CW Logs (same as admin audit) | Syslog text |

The Syslog VPCE path (June 2026) handles **admin audit and EMS events only** — not NFS/SMB file access operations.

---

## Architecture Options for Large-Volume File Access Logs

For environments with high file access audit volume (e.g., 71 GB GZIP/day):

### Option 1: Step Functions Distributed Map + Lambda (Recommended for EC2 elimination)

```
ONTAP volume (EVTX)
  → FSx for ONTAP S3 AP (read)
  → Step Functions Distributed Map
  → Lambda (per-file: EVTX → JSON)
  → S3 standard bucket (JSON output)
  → Athena (query)
```

- Parallelism: up to 10,000 concurrent Lambda invocations
- Processing time: 40 min (EC2) → minutes (Lambda parallel)
- Cost: Lambda execution + S3 storage (comparable to EC2)
- This project's EVTX parser: `shared/lambda-layers/log-parser/`

### Option 2: XML Format + Glue (Simplest if format change acceptable)

```
ONTAP volume (XML) ← vserver audit modify -format xml
  → FSx for ONTAP S3 AP (read)
  → Glue Crawler (XML natively supported)
  → Parquet (S3)
  → Athena (fast columnar query)
```

- Requires: `vserver audit modify -format xml` (ONTAP config change)
- Trade-off: XML files are 2-3x larger than EVTX; loses Event Viewer compatibility
- Note: ONTAP supports only ONE format per SVM (cannot run EVTX + XML simultaneously)

### Option 3: ECS Fargate Batch (Drop-in EC2 replacement)

```
ONTAP volume (EVTX)
  → FSx for ONTAP S3 AP (read)
  → EventBridge Schedule → ECS Fargate Task
  → Same conversion logic as current EC2
  → S3 standard bucket (JSON)
  → Athena
```

- Simplest migration: same code, different compute
- No instance management, patching, or SSH access needed

### Option 4: Hybrid — Full volume to S3/Athena + Security events to CloudWatch Logs

```
ONTAP volume (EVTX)
  → FSx for ONTAP S3 AP
  → Lambda (EVTX → JSON)
      |
      +→ ALL events: S3 standard bucket → Athena (compliance, full query)
      |
      +→ FILTERED (failures, deletes, high-priv only): CloudWatch Logs
           → Logs Insights (interactive)
           → Log Alarm (real-time detection)
           → Automated Response (user/IP blocking)
```

- Best of both worlds: low-cost bulk storage + real-time security detection
- CloudWatch Logs receives only 1-5% of total volume (cost-effective)

---

## Cost Comparison (71 GB GZIP/day ≈ 200-300 GB expanded)

| Approach | Monthly Cost | Notes |
|----------|-------------|-------|
| Current: EC2 batch (40 min/day) | ~$100-150 | EC2 + S3 + Athena |
| All to CloudWatch Logs | **$4,500-7,000** | CW Logs ingestion $0.76/GB × 200-300 GB/day |
| Option 1: Step Functions + Lambda → S3 + Athena | ~$100-200 | Lambda + S3 + Athena (no EC2) |
| Option 4: Hybrid (full→S3, filtered→CW) | ~$150-250 | Adds CW Logs cost for filtered subset only |

> **Key insight**: Sending the full 71 GB/day to CloudWatch Logs is cost-prohibitive (~$5,000/month). The practical approach is to keep bulk data in S3 (for Athena) and send only security-relevant events to CloudWatch Logs (for real-time detection and alarming).

---

## ONTAP Audit Format Configuration

```bash
# Check current format
ssh fsxadmin@<management-ip>
vserver audit show -vserver <svm-name> -fields format

# Change to XML (if choosing Option 2)
vserver audit modify -vserver <svm-name> -format xml

# Note: Only affects NEWLY generated log files.
# Existing EVTX files are not converted.
# Cannot run EVTX + XML simultaneously on the same SVM.
```

---

## FAQ

**Q: Can FSx for ONTAP send file access audit logs directly to CloudWatch Logs?**
A: No. Only admin audit logs (via Syslog VPCE) can go directly to CloudWatch Logs. File access audit logs are stored as files on the ONTAP volume and must be read via FSx for ONTAP S3 AP, then processed by Lambda/ECS/Glue.

**Q: Can Glue read EVTX format?**
A: No. Glue does not natively support EVTX (Windows Event Log binary). To use Glue, change the ONTAP audit format to XML (`vserver audit modify -format xml`). Glue supports XML natively.

**Q: What about the blog that says FSx sends JSON to CloudWatch?**
A: That refers to FSx for Windows File Server, which has built-in CloudWatch Logs integration. Even there, the format is XML (not JSON) — but delivery is managed by AWS without any intermediary.

**Q: What is the most cost-effective way to eliminate EC2 for 71 GB/day EVTX processing?**
A: Step Functions Distributed Map + Lambda (Option 1). Processes files in parallel, eliminates EC2, and outputs JSON to S3 for Athena. Processing time drops from 40 minutes to a few minutes.

---

## Related Documents

- [Event Sources Guide](event-sources.md)
- [EMS Detection Capabilities](ems-detection-capabilities.md) — Push delivery for admin audit + EMS
- [Architecture Evolution: Syslog VPCE](../ja/architecture-evolution-syslog-vpce.md)
- [AWS Docs: FSx for ONTAP File Access Auditing](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)
- [AWS Docs: FSx for Windows File Access Auditing](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/file-access-auditing.html)
