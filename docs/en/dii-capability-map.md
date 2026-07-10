# DII Storage Workload Security — Capability Map & Parity Analysis

🌐 [日本語](../ja/dii-capability-map.md) | **English** (this page)

## Why This Document Exists

Prior additions to this repository referenced NetApp DII (Data Infrastructure Insights) Storage Workload Security in several places — a comparison table in the [Automated Response Guide](automated-response-guide.md), callouts in the root README, and a mention in the [NetApp Console<!-- allow:naming --> integration](../../integrations/netapp-console/). Each of those additions covered one slice of DII (mostly the *containment/response* side) without first laying out what DII actually does end-to-end. The result was piecemeal coverage: readers could find "how to block a user like DII does" but not "what does DII do overall, and which parts does this repo already cover vs. still need work."

This document fixes that by first mapping DII SWS's full capability set, then showing — phase by phase — what this repository already provides, what requires assembling existing pieces, and what is a genuine gap. Read this document first; it links out to the detailed how-to guides for each phase rather than duplicating them.

> **Evidence tier**: DII SWS's capability descriptions below are drawn from NetApp's public documentation (linked per claim). This repo's "equivalent" column reflects functionality that exists and is E2E-verified in this codebase unless marked otherwise.

> **Onboarding note**: If you're new to this repository, read this document's tables top-to-bottom before jumping into any linked implementation guide — the ✅/⚠️/❌ status markers tell you upfront whether a capability is ready to deploy, needs assembly work, or isn't available, which saves a round trip of reading a detailed guide only to discover it doesn't cover what you needed. Once you've picked a row that interests you, the fastest path to a working deployment is usually: clone the repo, read that row's linked guide's own Prerequisites and Deployment sections, then come back here only if you need the broader CSF 2.0 context. You don't need to read the CSF 2.0 background sections below to deploy anything — they explain *why* this document is organized the way it is, not *how* to deploy.

> **Documentation-density note**: This document now carries three tables (CSF 2.0 Function Mapping, the NIST SP 800-61 phase table, and the Capability Parity Table) plus a growing set of inline topic notes accumulated across multiple review passes. That density is intentional — it lets a reader pick the resolution they need (CSF 2.0 for an executive/compliance audience, SP 800-61 for an operational one, the per-row status for a hands-on deployer) — but it also means a reader skimming rather than reading top-to-bottom can miss a caveat that's specific to one table and not repeated in the others. If you're citing a specific claim from this document elsewhere (a blog post, an internal wiki, a customer-facing deck), link to the specific table/row rather than paraphrasing from memory, since several rows carry qualifiers (fast pre-filter, not deep inspection; discovery, not remediation) that are easy to drop when summarizing.

## Where This Fits in Cyber Resilience: NIST CSF 2.0

Before zooming into DII SWS's specific phases, it helps to place both DII and this repository inside a broader cyber-resilience frame. The [NIST Cybersecurity Framework (CSF) 2.0](https://www.nist.gov/cyberframework) organizes an organization's *entire* cybersecurity risk-management program into six functions — **Govern, Identify, Protect, Detect, Respond, Recover** — and NIST has published a dedicated ransomware profile against it, [NIST IR 8374r1 — Ransomware Risk Management: A Cybersecurity Framework 2.0 Community Profile](https://csrc.nist.gov/pubs/ir/8374/r1/final). Cloud and storage vendors commonly publish their own CSF mappings for the same reason this document exists — to show customers which functions their tooling covers and which remain an organizational responsibility. AWS publishes [Ransomware Risk Management on AWS Using the NIST CSF](https://docs.aws.amazon.com/whitepapers/latest/ransomware-risk-management-on-aws-using-nist-csf/technical-capabilities.html), which maps AWS services to technical capabilities (Backup, Event detection, Forensics and analytics, Mitigation and containment, and others) organized by CSF function. NetApp publishes a similar walk-through mapping BlueXP<!-- allow:naming -->, ONTAP, and DII SWS to each CSF function (source: [Fortify your cybersecurity defenses with NIST framework](https://www.netapp.com/it/blog/fortify-cybersecurity-nist-framework/)).

### How CSF 2.0 Relates to the NIST SP 800-61 Mapping Below

This document already maps DII SWS onto the NIST SP 800-61 incident-response lifecycle (Protect → Detect → Contain/Respond → Recover) because that is the more granular, operational framing for comparing containment mechanics. **CSF 2.0 and SP 800-61 are not competing frameworks — they operate at different altitudes.** CSF 2.0 is the organization-wide risk-management wheel that Govern sits above; SP 800-61 is the tactical incident-handling process that CSF's Detect/Respond/Recover functions delegate to during an actual event. Reading this document top-down: the CSF 2.0 table below tells you which organizational function each capability serves; the SP 800-61-based Capability Parity Table further down gives the operational detail within Detect/Respond/Recover.

### CSF 2.0 Function Mapping

| CSF 2.0 Function | Ransomware-Relevant Outcome | DII SWS Approach | This Repo's Approach | Status |
|-------------------|------------------------------|-------------------|------------------------|--------|
| **Govern (GV)** | Risk-management strategy, roles, policy, and oversight are established and communicated | Not a DII SWS capability — governance is an organizational function DII's tooling supports but doesn't provide | Not provided by this repo either — this is an observability/response *pipeline*, not a governance program. CloudFormation-as-code and CloudWatch Logs audit trails supply evidence artifacts (who deployed what, when a block fired and why) that a GV program can consume, but strategy, roles, and board-level reporting remain your organization's responsibility | ⚠️ Out of scope by design — see [Governance & Compliance](governance-and-compliance.md) and [Compliance Evidence Pack](compliance-evidence-pack.md) for the evidence layer |
| **Identify (ID)** | Assets, data, and dependencies that matter are inventoried and understood | BlueXP<!-- allow:naming --> data classification scans and categorizes data across storage, mapping it to workload importance | [Data Classification Guide](data-classification.md) defines a field-level classification matrix (PII/Sensitive/Internal); the [Content-Level PII Classification Scanner](content-classification-scanner.md) adds content-level discovery via Amazon Comprehend `DetectPiiEntities`, scoped to plain-text/structured-data formats (no document-format parsing — see that guide's Remaining Limitations) | ✅ Full for schema-level classification and text/structured-data content scanning; document-format (Office/PDF) content extraction remains unimplemented |

> **Privacy note**: "Full" for content scanning covers *discovery* — finding PII-shaped content and recording entity type/confidence, never the matched values themselves (data-minimizing by design). It does not cover the judgment calls a DPO/privacy program still owns: which confidence threshold counts as "found" for a given regulation, whether a false positive needs a compliance-log correction, or how discovered PII maps to a legal basis for processing. Treat the scanner's report as an input to that program, not a replacement for it.

> **Data-pipeline note**: If you plan to build reporting or dashboards on top of the PII scanner's DynamoDB output (e.g., a fleet-wide "where is PII" view aggregating multiple scan reports), read the [Content-Level PII Classification Scanner](content-classification-scanner.md)'s own Data-pipeline note first — confidence scores are persisted as DynamoDB strings, not numbers, due to a `parse_float=str` workaround in the Lambda code, which breaks numeric filtering/sorting on that field unless you cast explicitly at query time.
| **Protect (PR)** | Safeguards limit the likelihood and impact of an event | Per-user access baseline (passive monitoring); relies on ONTAP's own Snapshot/SnapLock immutability underneath | Proactive ONTAP-native controls (export-policy, name-mapping) plus the same underlying Snapshot/SnapLock immutability ONTAP provides — this is a shared ONTAP platform capability, not DII- or repo-specific | ✅ Full for storage-layer safeguards (shared ONTAP mechanism); IAM least-privilege and Secrets Manager rotation cover the pipeline's own attack surface — see [Security Considerations](automated-response-guide.md#security-considerations) |
| **Detect (DE)** | Anomalies and adverse events are found through continuous monitoring | ML-based per-user behavioral anomaly detection (SaaS backend) plus ARP alert integration | ONTAP ARP (native ransomware signature/entropy detection) + EMS event catalog + delegated SIEM ML (Datadog Watchdog, Elastic ML Jobs, Splunk MLTK) | ⚠️ Requires assembly for behavioral ML (see Capability Parity Table below); ✅ Full for signature/entropy-based and quota-anomaly detection |
| **Respond (RS)** | Actions are taken on a detected incident: analysis, mitigation, and reporting | Automated user/IP block + protective snapshot + admin alert, driven by DII's own ML detection | Same ONTAP blocking/snapshot mechanisms, triggerable from *any* detection source via SNS — see [Automated Response Guide](automated-response-guide.md); Forensics dashboards (this document) serve the RS.AN (analysis) sub-function | ✅ Full for mitigation and analysis tooling |
| **Recover (RC)** | Systems and data are restored, and recovery is coordinated with stakeholders (CSF 2.0 splits this into RC.RP — Incident Recovery Plan Execution — and RC.CO — Incident Recovery Communication) | Automatic detection-time snapshot simplifies restoration; no published RC.CO tooling beyond alerts | Protective snapshot exists (RS phase); the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) closes the RC.RP gap by cloning the candidate snapshot (FlexClone), scanning it via an isolated S3 Access Point for ransomware indicators, and recording a clean/suspicious/error verdict — before a human commits to a restore. SNS notification covers a minimal RC.CO signal, not stakeholder-level recovery coordination | ✅ Full for RC.RP verification (fast pre-filter, not a full forensic scan — see that guide's Comparison section); ⚠️ RC.CO stakeholder coordination remains a minimal SNS signal |

> **Restore-testing note**: "RC.RP verification: Full" above means the automated extension-pattern pre-filter is fully implemented — it does not mean recoverability itself is fully proven. Running an actual restore (mounting the recovered volume, validating application-level data integrity, timing the operation against your RTO) is still a separate, periodic exercise this repo does not automate. Treat the verification workflow's "clean" verdict as the gate that decides *whether* a snapshot is worth spending a restore-rehearsal cycle on, not as a substitute for running that rehearsal.

> **DR-runbook sequencing note**: This table's RC.RP row describes a technical capability, not a DR runbook step — deploying the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) does not by itself change how your organization decides to fail over or restore during an actual incident, unless you explicitly update your DR runbook to gate on this workflow's verdict (see that guide's own DR-runbook sequencing note for the specific sequencing question). Treat the ✅ in this table as "the building block exists," not "your DR plan already uses it."

> **Resilience-maturity note**: Industry analysis of CSF 2.0's RECOVER function (e.g., [Elastio's mapping of ransomware recovery to CSF 2.0](https://elastio.com/blog/mapping-ransomware-recovery-to-nist-csf-20)) makes a point worth internalizing here: a snapshot or backup existing is a **Protect** artifact, not evidence that RC.RP is operationally credible. RC.RP is only credible once you can point to a recovery point that has actually been tested and confirmed free of compromise — not merely a completed snapshot job. The automated-response module creates protective snapshots (Respond phase); the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) adds the missing verification step (FlexClone + isolated scan + recorded verdict). Treat "snapshot created" and "verified clean recovery point, tested" as two different maturity levels — this repo now delivers both, though the verification is a fast extension-based pre-filter, not a full forensic-grade content scan (see that guide's Comparison and FAQ for the precise boundary).

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

> **Threat-intelligence note**: Entropy/extension-change analysis (ARP) and behavioral ML (DII's own approach) sit on opposite ends of a detection tradeoff worth naming explicitly: entropy-based detection generalizes well to *novel* ransomware families it has never seen (encryption inherently raises file entropy regardless of which malware caused it), while behavioral ML generalizes well to detecting *anomalous access patterns* even from an attacker using no encryption at all (e.g., mass exfiltration without encryption, a growing tactic in double-extortion campaigns). Neither approach alone covers both cases well. This repo's [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) scan, layered on top of ARP, adds a third, narrower signature-list-based check (specific known extensions) — see that guide's own Threat-intelligence note for why that third layer has the most evasion-prone blind spot of the three.

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
| Recover | Fast restore from detection-time snapshot | Manual `volume snapshot restore` from the protective snapshot created during Respond | ⚠️ Requires assembly — restore itself remains a manual ONTAP operation | [Remaining Gaps](#remaining-gaps-not-yet-addressed), item 3 |
| Recover | Verified-clean recovery point (RC.RP) before restore | FlexClone + isolated S3 Access Point scan + recorded verdict | ✅ Full (fast pre-filter, not a full forensic scan) | [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) |
| Identify | Content-level PII/data classification | Amazon Comprehend `DetectPiiEntities` via S3 Access Point | ✅ Full for text/structured-data formats; ❌ Gap for Office/PDF content extraction | [Content-Level PII Classification Scanner](content-classification-scanner.md) |
| Forensics | Forensic User Overview (per-user activity summary) | Buildable from normalized `user`/`client_ip`/`path`/`operation` fields already present in the audit-log and FPolicy pipelines | ⚠️ Requires assembly — see per-vendor guidance | [Per-Vendor Forensics Dashboard Implementation](#per-vendor-forensics-dashboard-implementation) |
| Forensics | All Activity (chronological, filterable) | Same underlying fields; needs a dashboard/saved-search per vendor | ⚠️ Requires assembly | [Per-Vendor Forensics Dashboard Implementation](#per-vendor-forensics-dashboard-implementation), "Forensics - All Activity" row per vendor |
| Forensics | User Activity Data (drill-down) | Same underlying fields | ⚠️ Requires assembly | [Per-Vendor Forensics Dashboard Implementation](#per-vendor-forensics-dashboard-implementation), IP-centric drill-down per vendor (e.g. Splunk `ip-centric-activity.spl`) |
| Forensics | Entities Page (file/object-centric history) | Same underlying fields, grouped by `path` instead of `user` | ⚠️ Requires assembly | [Per-Vendor Forensics Dashboard Implementation](#per-vendor-forensics-dashboard-implementation), file-centric view per vendor (e.g. Splunk `file-entity-history.spl`) |
| Forensics | 31-day filtered CSV export | Vendor-native export (Datadog Log Explorer export, Splunk `outputcsv`, Kibana Discover CSV, Grafana panel export) — retention depends on your configured index/retention policy, not a 31-day hard limit | ✅ Full (vendor-native, often *better* than DII's fixed window) | [Per-Vendor Forensics Dashboard Implementation](#per-vendor-forensics-dashboard-implementation) |

Legend: ✅ Full = same or superior capability exists and is documented/verified. ⚠️ Requires assembly = the underlying data exists but no pre-built dashboard/runbook ships yet — the [Per-Vendor Forensics Dashboard Implementation](#per-vendor-forensics-dashboard-implementation) section below provides the Forensics dashboards themselves (Splunk `.spl` searches, a Datadog Notebook, a Grafana dashboard JSON, Elastic Kibana saved searches); the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) provides the restore-verification runbook. ❌ Gap = genuinely not available; would require new development.

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

## Remaining Gaps (Not Yet Addressed)

Being direct about what this repo does **not** provide, so this document doesn't overstate parity:

1. **No built-in per-user behavioral ML model.** DII SWS ships a trained anomaly-detection model; this repo requires you to configure and train your SIEM's ML feature (Datadog Watchdog, Elastic ML Jobs, Splunk MLTK) separately, or rely on threshold-based detection (see [Detection Use Cases](detection-use-cases.md)), which has different false-positive characteristics than behavioral baselining.
2. **No pre-built unified dashboard across all data — buildable, not shipped.** This repo is inherently multi-vendor: if you ship to more than one SIEM, forensic investigation happens per-vendor today, not in one pane of glass. This is a packaging gap, not a technical ceiling. Two paths close it: (a) route every vendor through the [OTel Collector integration](../../integrations/otel-collector/) into a single OTLP-native backend, which gets you back to one UI at the cost of that backend becoming your single point of query; or (b) since every vendor pipeline emits the same [Normalized Event Schema](normalized-event-schema.md) fields (`source`, `svm`, `user`, `path`, `operation`), a query layer that reads across vendor-specific stores (e.g., Athena over exported logs, or a BI tool with per-vendor connectors) can reconstruct a unified view without picking one vendor as the source of truth. Neither ships pre-built in this repo today.
3. **Snapshot-restore verification is a fast pre-filter, not a full forensic-grade scan or an end-to-end restore rehearsal.** The [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) closes the original "no verified-clean recovery point workflow" gap by cloning the candidate snapshot (FlexClone), scanning it via an isolated S3 Access Point for ransomware-associated file extensions, and recording a clean/suspicious/error verdict before a human commits to a restore. What remains genuinely unaddressed: the scan is extension-pattern matching, not deep content inspection, and no actual restore is exercised end-to-end — see that guide's Comparison section for the precise boundary of what "verified" means here.
4. **No pre-built cross-storage-system view — buildable, not shipped.** DII SWS can span an on-prem + cloud fleet from one tenant natively. This repo is scoped to FSx for ONTAP by default; other NetApp systems (on-prem ONTAP, other FSx for ONTAP file systems, other regions/accounts) are not correlated out of the box. This is a scope-of-delivery gap, not a technical ceiling: the same audit-log/FPolicy pipelines in this repo can be deployed against any ONTAP-based system (on-prem or cloud) that exposes an FPolicy/audit-log path, and the [Multi-Account Deployment](multi-account-deployment.md) StackSets pattern already fans this pipeline out across AWS accounts and regions. Tag each deployment's events with a distinguishing `source`/`svm` value (see [Normalized Event Schema](normalized-event-schema.md)) and aggregate at the vendor/query layer to get a fleet-wide view — this repo does not ship that aggregation dashboard, but nothing in the architecture prevents building one.

> **Multi-cloud-scope note**: The "any ONTAP-based system" claim above is scoped to ONTAP running on AWS (FSx for ONTAP) or on-prem ONTAP with a network path reachable from this repo's Lambdas/ECS tasks — it does not extend to ONTAP offerings on other hyperscalers (e.g., Azure NetApp Files, Google Cloud NetApp Volumes) without adapting the network/IAM layer to that platform's equivalents, since this repo's audit-log and FPolicy pipelines are built on AWS-native services (Lambda, EventBridge Scheduler, ECS Fargate) rather than a cloud-agnostic collector. If your fleet spans multiple hyperscalers, treat this repo as the AWS-side collector in a broader multi-cloud observability design, not as a single pipeline that already spans clouds.

> **Data-residency note**: The [Multi-Account Deployment](multi-account-deployment.md) StackSets pattern referenced above fans this repo's pipelines out across AWS accounts *and Regions* — which is directly useful for a residency requirement that data from a given jurisdiction stay within a specific Region's boundary, since each StackSet-deployed stack instance operates independently within its own target Region. What this repo does not provide is any built-in verification that a given deployment's data actually stayed within its intended Region boundary — that verification (confirming no cross-Region replication was inadvertently configured, confirming the FSx for ONTAP file system itself is in the intended Region) remains a deployment-time configuration discipline you own, not something this repo's tooling checks for you.

> **Resource-tagging note**: Fanning these pipelines out across accounts/Regions via StackSets (as referenced above) multiplies any existing tagging gaps across every stack instance — both the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) and [Content-Level PII Classification Scanner](content-classification-scanner.md) templates only tag their DynamoDB tables, leaving Lambda functions (and, for the recovery guide, the Step Functions state machine) untagged in this repo's current templates. If your organization enforces tagging policy at the StackSet/OU level, add the missing `Tags` blocks (see each guide's own resource-tagging note) before fanning these templates out at scale, rather than discovering the gap once tagging-policy enforcement blocks a StackSet deployment across dozens of accounts.

> **Patch-management note**: This repo's various Lambda functions each pin `python3.12` as the runtime but do not pin exact `boto3`/`botocore` package versions in their inline CloudFormation `ZipFile` code — Lambda's managed Python runtime bundles a current SDK version at deploy time, which drifts forward as AWS updates the managed runtime. This is convenient (no manual dependency bumps required to pick up SDK bug/security fixes) but also means two identical deploys weeks apart may not run byte-identical SDK code, and a deploy today does not guarantee the exact same behavior after AWS updates the `python3.12` managed runtime in place. If your organization requires pinned, auditable dependency versions for every deployed artifact, package these Lambdas with a `requirements.txt`-pinned deployment (Lambda Layers or a container image) instead of relying on the inline `ZipFile` + managed-runtime SDK approach these CloudFormation templates currently use.

> **Security note**: The [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s ONTAP-facing Lambdas disable TLS certificate verification (`cert_reqs="CERT_NONE"`) unconditionally in their inline CloudFormation code — see that guide's own security note under Prerequisites for the specific fix required before production use. This is called out here as well because it's the kind of finding that a security review of *this* document's Capability Parity Table alone would miss: the table's ✅ marks for RC.RP verification describe functional completeness, not security hardening completeness, and a security reviewer relying solely on this document's status markers would not learn that a linked implementation carries a must-fix TLS finding. If you're using this document to plan a security review's scope, plan to read each linked guide's own Security Considerations section, not just this document's summary tables.
5. **Content-level PII discovery covers text/structured-data formats only — not a hard ceiling.** The [Content-Level PII Classification Scanner](content-classification-scanner.md) closes the original "no content-level classification" gap for `.txt`/`.csv`/`.json`/`.log` and similar formats via Amazon Comprehend `DetectPiiEntities`, complementing this repo's [Data Classification Guide](data-classification.md) schema-level (field-name) classification. What remains unaddressed: Office documents and PDFs are not text-extracted, so content-level PII in those formats is not detected today. This is a missing pre-processing step, not a limitation of Comprehend or the scan itself — feeding extracted text from Amazon Textract (or a document-parsing Lambda Layer) into this scanner's existing `classify_object` logic would cover those formats too; see that guide's Remaining Limitations and FAQ sections for the specific extension point.
6. **No Govern-function tooling.** Risk-management strategy, policy, and board-level reporting (CSF 2.0 Govern) remain an organizational responsibility this repo does not attempt to automate — no storage-layer tool, DII SWS included, can substitute for that program. See the CSF 2.0 Function Mapping table above.

## FAQ

**Q: Do I need all four vendor implementations (Splunk, Datadog, Grafana, Elastic)?**
A: No — build the Forensics dashboard only for whichever SIEM(s) you already ship audit/FPolicy events to. This document covers all four because the repo supports all four as ingestion targets, not because you need all four simultaneously.

**Q: Does this replace DII SWS's Detect phase (the ML model) too?**
A: No. This document is explicit that the ML behavioral baseline is a remaining gap (see Remaining Gaps, item 1). If per-user ML anomaly detection without manual threshold tuning is a hard requirement, DII SWS (or your SIEM's equivalent ML feature, separately configured) remains necessary. What this repo replaces is the *Respond* mechanism and the *Forensics* investigation surface, using the same underlying ONTAP APIs and the same underlying FPolicy/audit data DII itself uses.

**Q: Why does the Forensics section reference the same NetApp KB limitations as this repo's own known gaps?**
A: Because both DII SWS and this repo's FPolicy pipeline ultimately depend on the same ONTAP FPolicy mechanism. Any operation invisible to FPolicy (API-driven changes, NFS 4.1) is invisible to *both* systems — this is a shared platform limitation, not something either implementation solves differently.

**Q: Where does CSF 2.0's Govern function fit, since this document doesn't cover it?**
A: It doesn't — deliberately. Govern (risk-management strategy, roles, policy, board oversight) is an organizational responsibility that no storage-layer tool, DII SWS included, can automate on your behalf. This document's CSF 2.0 table marks Govern as out of scope by design and points to [Governance & Compliance](governance-and-compliance.md) and the [Compliance Evidence Pack](compliance-evidence-pack.md) for the evidence artifacts (audit trails, deployment-as-code, block/response logs) that a Govern program would consume as input, not as a substitute for the program itself.

**Q: The Capability Parity Table marks RC.RP verification and content-level PII discovery as "✅ Full" — does that mean those problems are solved end-to-end?**
A: "Full" means the specific capability in that row is fully implemented and E2E-verified — it does not mean the broader problem the row's phase addresses is closed. RC.RP verification is a fast, automated pre-filter; an actual restore rehearsal (validating the recovered volume mounts and the application on top of it works) is a separate, periodic exercise this repo doesn't automate — see the Restore-testing note above. Content-level PII discovery similarly stops at reporting entity type/confidence; deciding what confidence threshold constitutes "found" PII for your regulatory context, and acting on that finding, remains your data protection program's responsibility — see the Privacy note above.

**Q: How should this document be positioned to a customer or in a sales conversation?**
A: As a transparent gap analysis, not a marketing comparison — the ✅/⚠️/❌ markers exist specifically so this repo doesn't overstate parity with DII SWS (see the Why This Document Exists section above). The Customer-facing positioning notes in the linked implementation guides (see the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) and [Content-Level PII Classification Scanner](content-classification-scanner.md)) spell out the accurate one-sentence framing for each individual capability (e.g., the RC.RP verification workflow is a pre-filter, not a forensic certification). Lead with the ⚠️/❌ rows honestly in any customer-facing summary — the credibility of the ✅ rows depends on not glossing over the rows that aren't.

**Q: Can this document's ✅ markers be cited directly as evidence in an internal audit or SOX control matrix?**
A: Not directly — this document's ✅ marks that a *capability exists and is E2E-verified in this codebase*, which is a different claim than "this control operated effectively during the audit period at your organization." An auditor testing operating effectiveness needs evidence the deployed instance actually ran, was reviewed, and drove a documented decision — see the Audit-evidence notes in the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) and [Content-Level PII Classification Scanner](content-classification-scanner.md) for what additional evidence (execution history, human review/attestation) each linked capability needs beyond its own existence to support a formal control assertion.

## Related Documents

- [Automated Response Guide](automated-response-guide.md) — Respond-phase implementation (this repo's most complete DII-parity area)
- [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) — RC.RP verification (FlexClone + isolated scan + recorded verdict), closing Remaining Gaps item 3
- [Content-Level PII Classification Scanner](content-classification-scanner.md) — Content-level PII discovery via Amazon Comprehend, closing Remaining Gaps item 5 for text/structured-data formats
- [ARP Incident Response Guide](arp-incident-response-guide.md) — Protect/Detect via ONTAP native ransomware detection
- [EMS Detection Capabilities](ems-detection-capabilities.md) — Detect-phase event catalog
- [Detection Use Cases](detection-use-cases.md) — Source selection for Detect-phase configuration
- [Normalized Event Schema](normalized-event-schema.md) — The shared field definitions underlying every Forensics implementation above
- [Data Classification Guide](data-classification.md) — PII handling for the user/IP/path fields shown in Forensics dashboards, and the schema-level classification the Content-Level PII Classification Scanner complements
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
