# DII Storage Workload Security — Capability Map & Parity Analysis

## Why This Document Exists

Prior additions to this repository referenced NetApp DII (Data Infrastructure Insights) Storage Workload Security in several places — a comparison table in the [Automated Response Guide](automated-response-guide.md), callouts in the root README, and a mention in the [NetApp Console<!-- allow:naming --> integration](../../integrations/netapp-console/). Each of those additions covered one slice of DII (mostly the *containment/response* side) without first laying out what DII actually does end-to-end. The result was piecemeal coverage: readers could find "how to block a user like DII does" but not "what does DII do overall, and which parts does this repo already cover vs. still need work."

This document fixes that by first mapping DII SWS's full capability set, then showing — phase by phase — what this repository already provides, what requires assembling existing pieces, and what is a genuine gap. Read this document first; it links out to the detailed how-to guides for each phase rather than duplicating them.

> **Evidence tier**: DII SWS's capability descriptions below are drawn from NetApp's public documentation (linked per claim). This repo's "equivalent" column reflects functionality that exists and is E2E-verified in this codebase unless marked otherwise.

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
3. **No packaged snapshot-restore runbook.** The Respond phase creates a protective snapshot; actually restoring from it during a Recover phase is a manual ONTAP operation not yet wrapped in a script or guide in this repo.
4. **No cross-storage-system view.** DII SWS can span an on-prem + cloud fleet from one tenant. This repo is scoped to FSx for ONTAP; if you have other NetApp systems, they are not correlated here.

## FAQ

**Q: Do I need all four vendor implementations (Splunk, Datadog, Grafana, Elastic)?**
A: No — build the Forensics dashboard only for whichever SIEM(s) you already ship audit/FPolicy events to. This document covers all four because the repo supports all four as ingestion targets, not because you need all four simultaneously.

**Q: Does this replace DII SWS's Detect phase (the ML model) too?**
A: No. This document is explicit that the ML behavioral baseline is a genuine gap (see Genuine Gaps, item 1). If per-user ML anomaly detection without manual threshold tuning is a hard requirement, DII SWS (or your SIEM's equivalent ML feature, separately configured) remains necessary. What this repo replaces is the *Respond* mechanism and the *Forensics* investigation surface, using the same underlying ONTAP APIs and the same underlying FPolicy/audit data DII itself uses.

**Q: Why does the Forensics section reference the same NetApp KB limitations as this repo's own known gaps?**
A: Because both DII SWS and this repo's FPolicy pipeline ultimately depend on the same ONTAP FPolicy mechanism. Any operation invisible to FPolicy (API-driven changes, NFS 4.1) is invisible to *both* systems — this is a shared platform limitation, not something either implementation solves differently.

## Related Documents

- [Automated Response Guide](automated-response-guide.md) — Respond-phase implementation (this repo's most complete DII-parity area)
- [ARP Incident Response Guide](arp-incident-response-guide.md) — Protect/Detect via ONTAP native ransomware detection
- [EMS Detection Capabilities](ems-detection-capabilities.md) — Detect-phase event catalog
- [Detection Use Cases](detection-use-cases.md) — Source selection for Detect-phase configuration
- [Normalized Event Schema](normalized-event-schema.md) — The shared field definitions underlying every Forensics implementation above
- [Data Classification Guide](data-classification.md) — PII handling for the user/IP/path fields shown in Forensics dashboards
- [Security Monitoring Index](security-monitoring-index.md) — Role-based navigation across all security docs
