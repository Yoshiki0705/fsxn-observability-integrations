# Existing Audit Tool Coexistence Guide

🌐 [日本語](../ja/existing-audit-tool-coexistence.md) | **English** (this page)

## Overview

This document describes how the serverless observability pipeline (Lambda + S3 Access Point + HEC/OTLP) coexists with existing batch-based audit log tools that may already be deployed in the environment.

The serverless pipeline is **not a drop-in replacement** for existing audit reporting tools. It provides a complementary detection and investigation path optimized for SOC use cases (real-time alerting, SIEM correlation, XDR integration). Existing tools may continue to serve audit reporting, compliance evidence, and internal investigation workflows.

---

## ONTAP Audit Format Constraint

**Critical**: ONTAP supports only one audit log output format per SVM. Each SVM's audit configuration uses either EVTX or XML — simultaneous dual-format output is not supported.

Reference: [NetApp KB — Can ONTAP generate CIFS audit logs in both EVTX and XML formats at the same time?](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Can_ONTAP_generate_CIFS_audit_logs_in_both_EVTX_and_XML_formats_at_the_same_time)

| Scenario | Format | Consumers |
|----------|--------|-----------|
| Existing tool requires EVTX | EVTX | Existing tool + Windows Event Viewer |
| This pipeline (serverless) | XML | Lambda parser (stdlib, no binary dependencies) |
| Both tools on same SVM | ❌ Not possible simultaneously | Must choose one format or use separate SVMs |

### Coexistence Strategies

| Strategy | Description | Trade-offs |
|----------|-------------|------------|
| **A: Separate SVMs** | Dedicate one SVM for EVTX (existing tool) and another for XML (serverless pipeline). Use SnapMirror or qtree-level replication if needed. | Additional SVM overhead; clear ownership separation |
| **B: Format migration** | Migrate from EVTX to XML. Validate existing tool can consume XML or adapt. | Existing tool may not support XML |
| **C: Single format (EVTX) + Lambda EVTX parser** | Keep EVTX format. Use the `fsxn_log_parser` EVTX parsing path (limited field extraction without binary parser library). | Limited parser capability without `python-evtx` in Lambda Layer |
| **D: Normalized feed from existing tool** | Keep existing tool as primary collector. Export normalized access logs from the existing tool to the SIEM via HEC or file export. | Depends on existing tool's export capability |
| **E: S3 Access Point for both** | Both tools read from the same S3 Access Point (same format). Only works if both can consume the same format. | Requires format compatibility |

---

## Ownership Split: Reporting vs Detection

| Responsibility | Existing Audit Tool | Serverless Pipeline (This Project) |
|---------------|--------------------|------------------------------------|
| Audit reporting (monthly, quarterly) | ✅ Primary | ❌ Not designed for |
| Compliance evidence export | ✅ Primary | ⚠️ Possible via SIEM export |
| Internal investigation (who/when/what) | ✅ Primary | ✅ Complementary (real-time search) |
| SOC detection (mass delete, exfiltration) | ❌ Not designed for | ✅ Primary |
| XDR/EDR correlation | ❌ Not possible | ✅ Primary (Falcon, etc.) |
| Real-time alerting (<5 min) | ❌ Batch-based | ✅ Primary |
| Retention (long-term archive) | ✅ Primary | ⚠️ Depends on SIEM retention |
| User behavior summarization | ✅ Primary | ❌ Not designed for |
| Compression and storage optimization | ✅ Primary | ❌ Raw events in SIEM |

---

## Duplicate Collection Risk

If both the existing tool and this pipeline consume the same audit logs:

### Risks

1. **Inconsistent audit records** — If one tool processes a file before the other, and the file is rotated/deleted, one tool may miss events
2. **Double storage cost** — Same events stored in two systems
3. **Timestamp drift** — Different processing delays may make cross-referencing difficult
4. **Operational confusion** — Two "sources of truth" for the same events

### Mitigations

- **Clear ownership model**: Define which system is authoritative for which use case (reporting vs detection)
- **Shared audit volume**: Both tools read from the same source (S3 Access Point or NFS/SMB export) — no data duplication at source
- **Consistent timestamps**: Both tools should preserve the original ONTAP event timestamp, not ingest time
- **Runbook clarity**: Document which tool to use for which investigation scenario

---

## Retention and Evidence Policy

| Aspect | Existing Tool | Serverless Pipeline |
|--------|--------------|---------------------|
| Retention period | Per tool configuration (often 1-7 years for compliance) | Per SIEM retention (varies by vendor/contract) |
| Evidence export | Tool-specific report format | SIEM export (JSON, CSV) |
| Chain of custody | Tool manages internally | SIEM audit trail + CloudTrail |
| Tamper protection | Tool-specific (read-only archive) | SIEM immutable storage (varies) |

**Recommendation**: If audit logs are part of regulatory evidence (ISMAP, FISC, SOC 2), ensure at least one system provides tamper-resistant long-term retention with documented chain of custody.

---

## Migration Considerations

If migrating from an existing batch tool to this serverless pipeline:

1. **Validate functional parity** — This pipeline provides detection and search, not summarization or compliance report templates
2. **Validate format change impact** — Switching from EVTX to XML affects all consumers of that SVM's audit logs
3. **Plan parallel operation period** — Run both systems in parallel during validation
4. **Confirm retention requirements** — Ensure SIEM retention meets compliance requirements before decommissioning the existing tool's archive
5. **Document the decision** — Record why the migration was approved, what use cases transfer, and what gaps remain

---

## Decision Flowchart

```
┌─────────────────────────────────────────┐
│ Is an existing audit tool deployed?      │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴───────┐
       │ No            │ Yes
       ▼               ▼
┌──────────────┐  ┌──────────────────────────────────┐
│ Deploy XML   │  │ What format does it require?      │
│ pipeline     │  └──────────────┬───────────────────┘
│ directly     │         ┌───────┴───────┐
└──────────────┘         │ EVTX          │ XML / Either
                         ▼               ▼
              ┌────────────────┐  ┌──────────────────────┐
              │ Choose:         │  │ Deploy XML pipeline  │
              │ A: Separate SVM │  │ alongside existing   │
              │ C: EVTX parser  │  │ tool (same format)   │
              │ D: Normalized   │  └──────────────────────┘
              │    feed export  │
              └────────────────┘
```

---

## Partner Discovery Questions

When an existing audit tool is present, ask:

- What tool is currently deployed? (product name, version)
- Which SVMs and shares are covered?
- What is the current audit log format (EVTX or XML)?
- What reports are generated today? (monthly access, deletion tracking, sensitive folder monitoring)
- Who owns audit reporting vs security monitoring?
- Is the SIEM intended to replace, complement, or consume the existing tool's output?
- What is the retention requirement for audit evidence?
- Can the existing tool export a normalized feed (CSV, JSON, syslog) to a SIEM?

---

## References

- [NetApp KB: ONTAP Audit Format Limitation](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Can_ONTAP_generate_CIFS_audit_logs_in_both_EVTX_and_XML_formats_at_the_same_time)
- [NetApp Docs: Supported Audit Event Log Formats](https://docs.netapp.com/us-en/ontap/nas-audit/supported-audit-event-log-formats-concept.html)
- [AWS Docs: FSx for ONTAP File Access Auditing](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)
- [NetApp Docs: Create Auditing Configuration](https://docs.netapp.com/us-en/ontap/nas-audit/create-auditing-config-task.html)
