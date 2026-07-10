# DII Storage Workload Security — Capability Map & Parity Analysis

🌐 [日本語](../ja/dii-capability-map.md) | **English** (this page)

## Why This Document Exists

Prior additions to this repository referenced NetApp DII (Data Infrastructure Insights) Storage Workload Security in several places — a comparison table in the [Automated Response Guide](automated-response-guide.md), callouts in the root README, and a mention in the [NetApp Console<!-- allow:naming --> integration](../../integrations/netapp-console/). Each of those additions covered one slice of DII (mostly the *containment/response* side) without first laying out what DII actually does end-to-end. The result was piecemeal coverage: readers could find "how to block a user like DII does" but not "what does DII do overall, and which parts does this repo already cover vs. still need work."

This document fixes that by first mapping DII SWS's full capability set, then showing — phase by phase — what this repository already provides, what requires assembling existing pieces, and what is a genuine gap. Read this document first; it links out to the detailed how-to guides for each phase rather than duplicating them.

> **Evidence tier**: DII SWS's capability descriptions below are drawn from NetApp's public documentation (linked per claim). This repo's "equivalent" column reflects functionality that exists and is E2E-verified in this codebase unless marked otherwise.

## Where This Fits in Cyber Resilience: NIST CSF 2.0

Before zooming into DII SWS's specific phases, it helps to place both DII and this repository inside a broader cyber-resilience frame. The [NIST Cybersecurity Framework (CSF) 2.0](https://www.nist.gov/cyberframework) organizes an organization's *entire* cybersecurity risk-management program into six functions — **Govern, Identify, Protect, Detect, Respond, Recover** — and NIST has published a dedicated ransomware profile against it, [NIST IR 8374r1 — Ransomware Risk Management: A Cybersecurity Framework 2.0 Community Profile](https://csrc.nist.gov/pubs/ir/8374/r1/final). Cloud and storage vendors commonly publish their own CSF mappings for the same reason this document exists — to show customers which functions their tooling covers and which remain an organizational responsibility. AWS publishes [Ransomware Risk Management on AWS Using the NIST CSF](https://docs.aws.amazon.com/whitepapers/latest/ransomware-risk-management-on-aws-using-nist-csf/technical-capabilities.html), which maps AWS services to technical capabilities (Backup, Event detection, Forensics and analytics, Mitigation and containment, and others) organized by CSF function. NetApp publishes a similar walk-through mapping BlueXP<!-- allow:naming -->, ONTAP, and DII SWS to each CSF function (source: [Fortify your cybersecurity defenses with NIST framework](https://www.netapp.com/it/blog/fortify-cybersecurity-nist-framework/)).

### How CSF 2.0 Relates to the NIST SP 800-61 Mapping Below

This document already maps DII SWS onto the NIST SP 800-61 incident-response lifecycle (Protect → Detect → Contain/Respond → Recover) because that is the more granular, operational lens for comparing containment mechanics. **CSF 2.0 and SP 800-61 are not competing frameworks — they operate at different altitudes.** CSF 2.0 is the organization-wide risk-management wheel that Govern sits above; SP 800-61 is the tactical incident-handling process that CSF's Detect/Respond/Recover functions delegate to during an actual event. Reading this document top-down: the CSF 2.0 table below tells you which organizational function each capability serves; the SP 800-61-based Capability Parity Table further down gives the operational detail within Detect/Respond/Recover.

### CSF 2.0 Function Mapping

| CSF 2.0 Function | Ransomware-Relevant Outcome | DII SWS Approach | This Repo's Approach | Status |
|-------------------|------------------------------|-------------------|------------------------|--------|
| **Govern (GV)** | Risk-management strategy, roles, policy, and oversight are established and communicated | Not a DII SWS capability — governance is an organizational function DII's tooling supports but doesn't provide | Not provided by this repo either — this is an observability/response *pipeline*, not a governance program. CloudFormation-as-code and CloudWatch Logs audit trails supply evidence artifacts (who deployed what, when a block fired and why) that a GV program can consume, but strategy, roles, and board-level reporting remain your organization's responsibility | ⚠️ Out of scope by design — see [Governance & Compliance](governance-and-compliance.md) and [Compliance Evidence Pack](compliance-evidence-pack.md) for the evidence layer |
| **Identify (ID)** | Assets, data, and dependencies that matter are inventoried and understood | BlueXP<!-- allow:naming --> data classification scans and categorizes data across storage, mapping it to workload importance | [Data Classification Guide](data-classification.md) defines a field-level classification matrix (PII/Sensitive/Internal) for audit and FPolicy fields, but does not automatically scan/classify file *contents* the way BlueXP's classification service does | ⚠️ Requires assembly — schema-level classification exists; content-level discovery is a genuine gap |
| **Protect (PR)** | Safeguards limit the likelihood and impact of an event | Per-user access baseline (passive monitoring); relies on ONTAP's own Snapshot/SnapLock immutability underneath | Proactive ONTAP-native controls (export-policy, name-mapping) plus the same underlying Snapshot/SnapLock immutability ONTAP provides — this is a shared ONTAP platform capability, not DII- or repo-specific | ✅ Full for storage-layer safeguards (shared ONTAP mechanism); IAM least-privilege and Secrets Manager rotation cover the pipeline's own attack surface — see [Security Considerations](automated-response-guide.md#security-considerations) |
| **Detect (DE)** | Anomalies and adverse events are found through continuous monitoring | ML-based per-user behavioral anomaly detection (SaaS backend) plus ARP alert integration | ONTAP ARP (native ransomware signature/entropy detection) + EMS event catalog + delegated SIEM ML (Datadog Watchdog, Elastic ML Jobs, Splunk MLTK) | ⚠️ Requires assembly for behavioral ML (see Capability Parity Table below); ✅ Full for signature/entropy-based and quota-anomaly detection |
| **Respond (RS)** | Actions are taken on a detected incident: analysis, mitigation, and reporting | Automated user/IP block + protective snapshot + admin alert, driven by DII's own ML detection | Same ONTAP blocking/snapshot mechanisms, triggerable from *any* detection source via SNS — see [Automated Response Guide](automated-response-guide.md); Forensics dashboards (this document) serve the RS.AN (analysis) sub-function | ✅ Full for mitigation and analysis tooling |
| **Recover (RC)** | Systems and data are restored, and recovery is coordinated with stakeholders (CSF 2.0 splits this into RC.RP — Incident Recovery Plan Execution — and RC.CO — Incident Recovery Communication) | Automatic detection-time snapshot simplifies restoration; no published RC.CO tooling beyond alerts | Protective snapshot exists (RS phase), but this repo has **no tested, packaged restore runbook** — see Genuine Gaps below. SNS notification covers a minimal RC.CO signal, not stakeholder-level recovery coordination | ⚠️ Requires assembly for RC.RP; ❌ Gap for a *verified-clean* recovery point workflow |

> **Resilience-maturity lens**: Industry analysis of CSF 2.0's RECOVER function (e.g., [Elastio's mapping of ransomware recovery to CSF 2.0](https://elastio.com/blog/mapping-ransomware-recovery-to-nist-csf-20)) makes a point worth internalizing here: a snapshot or backup existing is a **Protect** artifact, not evidence that RC.RP is operationally credible. RC.RP is only credible once you can point to a recovery point that has actually been tested and confirmed free of compromise — not merely a completed snapshot job. This repo's automated-response module creates protective snapshots (Respond phase) but does not yet verify they are clean or exercise a restore against them. Treat "snapshot created" and "verified clean recovery point, tested" as two different maturity levels; this repo currently delivers the former.

The remainder of this document uses the more granular NIST SP 800-61 lifecycle (Protect/Detect/Respond/Recover/Forensics) already established below, since that is the appropriate resolution for comparing containment and investigation mechanics rather than organizational risk posture.

## DII Storage Workload Security: The Full Picture

DII SWS is one module within NetApp DII (formerly Cloud Insights). Per NetApp's own description, it "takes a user-centric approach, tracking all file activity from every authenticated user in the environment," using ML-established behavioral baselines to detect anomalies without ransomware signatures. Source: [Data Infrastructure Insights Storage Workload Security](https://docs.netapp.com/us-en/ontap-technical-reports/ransomware-solutions/ransomware-DII-workload-security.html).

Mapping DII SWS's stated capabilities onto the NIST SP 800-61 incident response lifecycle (Preparation/Protect → Detect → Contain/Respond → Recover), plus the Forensics investigation layer that spans all phases:

| Phase | What DII SWS Does | Underlying Mechanism |
|-------|-------------------|----------------------|
| **Protect** | Establishes per-user access baselines; integrates with ONTAP ARP alerts in a single interface | FPolicy data collector + ONTAP ARP webhook |
| **Detect** | ML-based behavioral anomaly detection (no signatures needed); flags deviation from a user's normal/seasonal access pattern | Per-user ML baseline model, cloud-hosted (SaaS backend) |
| **Respond** | Automatically blocks the suspected user account **and** IP address; takes a protective snapshot; alerts admins | Same ONTAP mechanisms as this repo: `name-mapping` (SMB), export-policy rules (NFS), `volume snapshot create` |
| **Recover** | Automatic snapshots taken at detection time simplify and accelerate restoration | ONTAP Snapshot restore (manual step after SWS's automatic snapshot) |
| **Forensics** (cross-cutting) | Dashboards showing which user, from which IP, touched which file/path, doing what action, when — filterable up to 31 days, CSV export | Data pulled from the FPolicy collector into DII's backend database; **CIFS/NFS operations only** — API-driven operations (System Manager, PowerShell API, cluster CLI) are explicitly **not** captured (source: [Forensics Activity FAQ](https://kb.netapp.com/Cloud/BlueXP/Cloud_Insights/FAQ:_Storage_Workload_Security_Forensics_Activity) <!-- allow:naming -->) |

Four Forensics views exist in DII SWS specifically (per the same FAQ): **Forensic User Overview**, **Forensics - All Activity**, **Forensic User Activity Data**, and **Forensic Entities Page** (file/object-centric view). This document's per-vendor implementation guidance below is organized to produce equivalents of these four views.

> **Important distinction**: DII's *Detect* phase uses per-user behavioral ML running in NetApp's SaaS backend. ONTAP's own Autonomous Ransomware Protection (ARP) — which this repo already integrates with in [ARP Incident Response Guide](arp-incident-response-guide.md) — uses file-content entropy/extension-change analysis, not per-user behavioral ML. DII SWS treats ARP alerts as one additional input surfaced in its interface, layered on top of its own ML. **These are two different detection mechanisms; ARP is not a substitute for user-behavior ML**, and this repo does not ship a per-user ML baseline model. See the Detect row below for what fills that role instead.

## Capability Parity Table

| Phase | DII SWS Capability | This Repo's Equivalent | Status | Where |
|-------|--------------------|-----------------------|--------|-------|
| Protect | Integrated ARP alert visibility | Native EMS webhook from ARP, delivered in ~30s | ✅ Full | [EMS Detection Capabilities](ems-detection-capabilities.md) |
| Protect | Per-user access baseline (passive) | Not applicable — no passive baselining without ML (see Detect) | ❌ Gap | — |
| Detect | ML-based behavioral anomaly detection | Delegated to your SIEM's ML/anomaly features (Datadog Watchdog, Elastic ML Jobs, Splunk MLTK) — **not built-in**, requires SIEM configuration and training data | ⚠️ Requires assembly | [Detection Use Cases](detection-use-cases.md) |
| Detect | File-content ransomware signature/entropy detection | ONTAP ARP (native, same mechanism DII also surfaces) | ✅ Full | [ARP Incident Response Guide](arp-incident-response-guide.md) |
| Detect | Quota/capacity anomaly | ONTAP EMS quota events | ✅ Full | [EMS Detection Capabilities](ems-detection-capabilities.md) |
| Respond | Automated user block (SMB) | `name-mapping` denial, same ONTAP API | ✅ Full | [Automated Response Guide](automated-response-guide.md) |
| Respond | Automated IP block (NFS) | export-policy deny rule, same ONTAP API | ✅ Full | [Automated Response Guide](automated-response-guide.md) |
| Respond | Protective snapshot on detection | `create_snapshot` action with storm-prevention cooldown | ✅ Full | [Automated Response Guide](automated-response-guide.md) |
| Respond | Admin alerting | SNS notification topic (any downstream: email, Slack, PagerDuty) | ✅ Full | [Automated Response Guide](automated-response-guide.md) |
| Respond | Time-limited access restriction | EventBridge Scheduler auto-unblock (companion TTL stack) | ✅ Full (see TTL limitation note in the guide) | [Automated Response Guide](automated-response-guide.md) |
| Recover | Fast restore from detection-time snapshot | Manual `volume snapshot restore` from the protective snapshot created during Respond | ⚠️ Requires assembly — no packaged restore runbook yet | See Gaps below |
| Forensics | Forensic User Overview (per-user activity summary) | Buildable from normalized `user`/`client_ip`/`path`/`operation` fields already present in the audit-log and FPolicy pipelines | ⚠️ Requires assembly — see per-vendor guidance below | This document, "Building the Forensics Layer" |
| Forensics | All Activity (chronological, filterable) | Same underlying fields; needs a dashboard/saved-search per vendor | ⚠️ Requires assembly | This document |
| Forensics | User Activity Data (drill-down) | Same underlying fields | ⚠️ Requires assembly | This document |
| Forensics | Entities Page (file/object-centric history) | Same underlying fields, grouped by `path` instead of `user` | ⚠️ Requires assembly | This document |
| Forensics | 31-day filtered CSV export | Vendor-native export (Datadog Log Explorer export, Splunk `outputcsv`, Kibana Discover CSV, Grafana panel export) — retention depends on your configured index/retention policy, not a 31-day hard limit | ✅ Full (vendor-native, often *better* than DII's fixed window) | Vendor docs below |

Legend: ✅ Full = same or superior capability exists and is documented/verified. ⚠️ Requires assembly = the underlying data exists but no pre-built dashboard/runbook ships yet — this document provides that. ❌ Gap = genuinely not available; would require new development.

## Why Forensics Is the Same Underlying Data, Twice

The reason DII's Forensics dashboards and this repo's audit pipeline can reach near-parity is that **both draw from the same data source**: an FPolicy collector watching CIFS/NFS operations. DII's own FAQ confirms the same blind spots this repo's [normalized-event-schema.md](normalized-event-schema.md) already documents:

| Limitation | DII SWS (per NetApp KB) | This Repo |
|-----------|------------------------|-----------|
| API-driven operations (System Manager, PowerShell API, cluster CLI) | Not captured by Forensics — visible only in raw ONTAP cluster logs | Same gap — FPolicy does not see API calls either; use audit logs (`EventID`-based) for API-driven change visibility instead |
| FPolicy agent down/disconnected | No Forensics data during the outage | Same — Lambda/ECS Fargate FPolicy handler outage means no FPolicy events, though the independent audit-log pipeline (EventBridge Scheduler) continues unaffected |
| `svm` / `user` field completeness | Not documented as a known issue in DII's FAQ | Documented gap in this repo: `svm` may show "unknown" if FPolicy can't resolve it from handshake context; `user` may be empty for some operations — see [Normalized Event Schema](normalized-event-schema.md#notes) |
| Protocol coverage | CIFS/NFS only (SWS data collector scope) | Same — FPolicy pipeline is CIFS/NFS; NFS 4.1 is explicitly unsupported by FPolicy per NetApp's own KB |

**Practical implication**: because audit logs and FPolicy are two independent pipelines in this repo (unlike DII, which is FPolicy-only for Forensics), you can cross-check FPolicy gaps against the audit-log pipeline's `EventID`-based records for the same file operation — a correlation option DII's single-collector architecture does not offer. This is called out again in the per-vendor guidance below.

## Building the Forensics Layer: Data Source Decision

Before configuring any vendor dashboard, decide which pipeline to query for forensic investigation:

| Pipeline | Granularity | Latency | Best For |
|----------|------------|---------|----------|
| **FPolicy** (`operation_type`, `file_path`, `client_ip`, `user`, `protocol`) | Action-level (create/write/rename/delete) | Sub-second, event-driven | "What action, right now" — matches DII's real-time Forensics feed most closely |
| **Audit Logs** (`operation`, `path`, `user`, `client_ip`, `result`) | Access-check level (ReadData/WriteData, Success/Failure) | Minutes (Scheduler interval + log rotation) | "What happened over the last N days" — better for the 31-day-style historical view; also the only source with `result: Failure` for access-denied forensics |

Most of DII's four Forensics views map most directly to the **FPolicy** pipeline (action-level, near-real-time). Use the **audit-log** pipeline as your correlation/completeness check, and as the primary source when you need failed-access-attempt detail (FPolicy notifications are typically for the operations ONTAP *permits*, not denials — check your ONTAP FPolicy policy configuration for whether denied operations are also sent).

> **PII/compliance cross-reference**: Before building any of the dashboards below, review the [Data Classification Guide](data-classification.md) — `user`/`UserName` is classified PII (High risk) and `path`/`ObjectName` is classified Sensitive in that guide's Field Classification Matrix. A forensics dashboard is, by definition, displaying these fields in raw form to investigators; restrict dashboard access via vendor RBAC accordingly (see the Vendor-Specific Data Controls table in that guide).

## Per-Vendor Forensics Dashboard Implementation

### Splunk

Splunk already has the closest starting point in this repo: `integrations/splunk-serverless/searches/failed-access-attempts.spl` and `last-access-by-user-path.spl` both group by `user`/`client_ip`/`path`/`operation`. Three additional searches complete the four-DII-view parity set:

| DII View Equivalent | Search File | Purpose |
|---------------------|-------------|---------|
| Forensic User Overview | [`user-activity-timeline.spl`](../../integrations/splunk-serverless/searches/user-activity-timeline.spl) | All activity for one user, chronological, across audit + FPolicy sourcetypes |
| Forensics - All Activity | `failed-access-attempts.spl` (existing) + `last-access-by-user-path.spl` (existing) | Aggregate views across all users |
| Forensic User Activity Data (drill-down by IP) | [`ip-centric-activity.spl`](../../integrations/splunk-serverless/searches/ip-centric-activity.spl) | All activity from one source IP, for lateral-movement / credential-compromise investigation |
| Forensic Entities Page (file-centric) | [`file-entity-history.spl`](../../integrations/splunk-serverless/searches/file-entity-history.spl) | All activity on one file/path, across all users who touched it |

Build a Splunk Dashboard Studio dashboard with each `.spl` file as a panel, using dashboard input tokens (`$user_tok$`, `$ip_tok$`, `$path_tok$`) so investigators type a value once and all panels filter accordingly — this most closely reproduces DII's click-through Forensics navigation.

### Datadog

Datadog's existing [Saved Views](../../integrations/datadog/README.md#saved-views) already include path-based views. Add a **Forensic Investigation** notebook (Datadog Notebooks, not a static dashboard) with these query cells in sequence, mirroring DII's User Overview → All Activity → drill-down flow:

```
# Cell 1 — User Overview
source:fsxn @user:"{{user}}"
# group by @operation, visualize as timeseries + top list

# Cell 2 — All Activity for that user (chronological)
source:fsxn @user:"{{user}}"
# Log Stream view, sorted by time ascending

# Cell 3 — IP-centric drill-down (if investigating lateral movement)
source:fsxn @client_ip:"{{client_ip}}"

# Cell 4 — Entity/file drill-down
source:fsxn @path:"{{path}}"
```

Use Datadog **Notebook variables** (`{{user}}`, `{{client_ip}}`, `{{path}}`) so the notebook is reusable per-incident rather than rebuilt each time. Export findings via Log Explorer's CSV export, scoped to your investigation time range.

### Grafana

Loki's label-cardinality constraint (already documented in [Normalized Event Schema](normalized-event-schema.md#vendor-specific-considerations)) means `user`, `client_ip`, and `path` must stay in the JSON log body, not as labels — so Forensics panels use LogQL with `| json` parsing rather than label filters. A dashboard is provided at [`integrations/grafana/dashboards/forensics-investigation.json`](../../integrations/grafana/dashboards/forensics-investigation.json) with:

- Template variables for `user`, `client_ip`, and `path` (free-text, not label-based dropdowns, for the cardinality reasons above)
- A "User Activity" logs panel: `{source="fsxn"} | json | user=~"$user"`
- An "IP-Centric Activity" logs panel: `{source="fsxn"} | json | client_ip=~"$client_ip"`
- A "File/Entity History" logs panel: `{source="fsxn"} | json | path=~"$path"`
- An "Operation Breakdown" bar chart grouped by `operation` for whichever filter is active

Import via **Dashboards → Import → Upload JSON file** in Grafana Cloud, or provision it alongside the existing [alerting rules](../../integrations/grafana/alerting/) using the same service account token.

### Elastic

Kibana Discover + Lens cover this without a custom dashboard build, since ECS field mapping (`user.name`, `source.ip`, `file.path`, `event.action`) is already defined in the [Normalized Event Schema](normalized-event-schema.md#vendor-mapping-matrix). See the [Elastic Setup Guide](../../integrations/elastic/docs/en/setup-guide.md#forensic-investigation-kibana-discoverlens) for the specific KQL saved searches and Lens visualizations (User Overview, All Activity, IP drill-down, Entity/file history) that complete the four-view parity set.

## Genuine Gaps (Not Yet Addressed)

Being direct about what this repo does **not** provide, so this document doesn't overstate parity:

1. **No built-in per-user behavioral ML model.** DII SWS ships a trained anomaly-detection model; this repo requires you to configure and train your SIEM's ML feature (Datadog Watchdog, Elastic ML Jobs, Splunk MLTK) separately, or rely on threshold-based detection (see [Detection Use Cases](detection-use-cases.md)), which has different false-positive characteristics than behavioral baselining.
2. **No single unified dashboard across all data.** DII presents one Forensics UI regardless of which storage system generated the event. This repo is inherently multi-vendor — if you ship to more than one SIEM, forensic investigation happens per-vendor, not in one pane of glass (the [OTel Collector integration](../../integrations/otel-collector/) reduces but does not eliminate this if you fan out to multiple backends).
3. **No packaged snapshot-restore runbook, and no verified-clean recovery point workflow.** The Respond phase creates a protective snapshot; actually restoring from it during a Recover phase is a manual ONTAP operation not yet wrapped in a script or guide in this repo. More importantly (per the CSF 2.0 RECOVER discussion above), this repo does not verify that a given snapshot is free of compromise before treating it as a restore candidate — the snapshot's existence is not the same as a tested, confirmed-clean recovery point.
4. **No cross-storage-system view.** DII SWS can span an on-prem + cloud fleet from one tenant. This repo is scoped to FSx for ONTAP; if you have other NetApp systems, they are not correlated here.
5. **No Govern-function tooling and no content-level data classification/discovery.** Risk-management strategy, policy, and board-level reporting (CSF 2.0 Govern) are organizational responsibilities this repo does not attempt to automate. Similarly, this repo's [Data Classification Guide](data-classification.md) defines a schema-level field classification (which *fields* are PII) but does not scan file *contents* the way BlueXP's<!-- allow:naming --> data classification service does for the CSF 2.0 Identify function.

## FAQ

**Q: Do I need all four vendor implementations (Splunk, Datadog, Grafana, Elastic)?**
A: No — build the Forensics dashboard only for whichever SIEM(s) you already ship audit/FPolicy events to. This document covers all four because the repo supports all four as ingestion targets, not because you need all four simultaneously.

**Q: Does this replace DII SWS's Detect phase (the ML model) too?**
A: No. This document is explicit that the ML behavioral baseline is a genuine gap (see Genuine Gaps, item 1). If per-user ML anomaly detection without manual threshold tuning is a hard requirement, DII SWS (or your SIEM's equivalent ML feature, separately configured) remains necessary. What this repo replaces is the *Respond* mechanism and the *Forensics* investigation surface, using the same underlying ONTAP APIs and the same underlying FPolicy/audit data DII itself uses.

**Q: Why does the Forensics section reference the same NetApp KB limitations as this repo's own known gaps?**
A: Because both DII SWS and this repo's FPolicy pipeline ultimately depend on the same ONTAP FPolicy mechanism. Any operation invisible to FPolicy (API-driven changes, NFS 4.1) is invisible to *both* systems — this is a shared platform limitation, not something either implementation solves differently.

**Q: Where does CSF 2.0's Govern function fit, since this document doesn't cover it?**
A: It doesn't — deliberately. Govern (risk-management strategy, roles, policy, board oversight) is an organizational responsibility that no storage-layer tool, DII SWS included, can automate on your behalf. This document's CSF 2.0 table marks Govern as out of scope by design and points to [Governance & Compliance](governance-and-compliance.md) and the [Compliance Evidence Pack](compliance-evidence-pack.md) for the evidence artifacts (audit trails, deployment-as-code, block/response logs) that a Govern program would consume as input, not as a substitute for the program itself.

## Related Documents

- [Automated Response Guide](automated-response-guide.md) — Respond-phase implementation (this repo's most complete DII-parity area)
- [ARP Incident Response Guide](arp-incident-response-guide.md) — Protect/Detect via ONTAP native ransomware detection
- [EMS Detection Capabilities](ems-detection-capabilities.md) — Detect-phase event catalog
- [Detection Use Cases](detection-use-cases.md) — Source selection for Detect-phase configuration
- [Normalized Event Schema](normalized-event-schema.md) — The shared field definitions underlying every Forensics implementation above
- [Data Classification Guide](data-classification.md) — PII handling for the user/IP/path fields shown in Forensics dashboards, and the Identify-function schema classification referenced above
- [Governance & Compliance](governance-and-compliance.md) — The Govern-function evidence layer this document defers to
- [Compliance Evidence Pack](compliance-evidence-pack.md) — Audit-trail evidence artifacts for Govern/RC.CO reporting
- [Security Monitoring Index](security-monitoring-index.md) — Role-based navigation across all security docs

## External References

- [NIST Cybersecurity Framework (CSF) 2.0](https://www.nist.gov/cyberframework)
- [NIST IR 8374r1 — Ransomware Risk Management: A Cybersecurity Framework 2.0 Community Profile](https://csrc.nist.gov/pubs/ir/8374/r1/final)
- [AWS — Ransomware Risk Management on AWS Using the NIST CSF](https://docs.aws.amazon.com/whitepapers/latest/ransomware-risk-management-on-aws-using-nist-csf/technical-capabilities.html)
- [NetApp — Fortify your cybersecurity defenses with NIST framework](https://www.netapp.com/it/blog/fortify-cybersecurity-nist-framework/)
- [NetApp — Data Infrastructure Insights Storage Workload Security](https://docs.netapp.com/us-en/ontap-technical-reports/ransomware-solutions/ransomware-DII-workload-security.html)
- [NetApp — Forensics Activity FAQ](https://kb.netapp.com/Cloud/BlueXP/Cloud_Insights/FAQ:_Storage_Workload_Security_Forensics_Activity) <!-- allow:naming -->
- [Elastio — Mapping Ransomware Recovery to NIST CSF 2.0](https://elastio.com/blog/mapping-ransomware-recovery-to-nist-csf-20)
