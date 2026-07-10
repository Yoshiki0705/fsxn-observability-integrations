# Architecture Decision Record: Direct Send vs OTel Collector

🌐 [日本語](../ja/architecture-decision.md) | **English** (this page)

## Decision Matrix

| Dimension | Direct Send | OTel Collector |
|-----------|-------------|----------------|
| **Simplicity** | ✅ Fewer components, Lambda → Backend | ⚠️ Additional infrastructure to manage |
| **Multi-backend** | ❌ Separate Lambda per backend | ✅ Single OTLP stream, fan-out at Collector |
| **Operational ownership** | Lambda team owns delivery | Platform team owns Collector |
| **Backend migration** | Code change + redeploy Lambda | Config change only (no code change) |
| **Backpressure** | Lambda timeout / retry only | Collector queue + retry + DLQ |
| **Failure isolation** | Backend failure affects Lambda | Backend failure isolated to exporter |
| **Credential management** | Each Lambda needs backend creds | Collector centralizes credentials |
| **Config governance** | Per-Lambda env vars / Secrets | Centralized YAML, CI-validated |

## Use Direct Send When

- Single backend destination with no plans to change
- Team owns both Lambda and backend operations
- Minimal operational overhead is the priority
- Event volume is low (< 100 events/min)
- No requirement for routing, filtering, or redaction
- Backend vendor provides a native AWS integration (e.g., Firehose destination)

## Use OTel Collector When

- Multiple backends receive the same log stream
- Backend migration is planned or likely
- Centralized credential management is required
- Routing/filtering logic should be decoupled from application code
- Platform team provides Collector as a shared service
- Compliance requires redaction or PII masking before delivery
- Backpressure handling and failure isolation are critical

## Production Ownership Questions

Before deploying OTel Collector in production, answer these questions:

| # | Question | Owner |
|---|----------|-------|
| 1 | Who operates the Collector (deploy, patch, scale)? | Platform / SRE team |
| 2 | What is the config approval flow? | PR review → CI validate → staged rollout |
| 3 | How is failure isolated between backends? | Per-exporter retry queue; one backend failure does not block others |
| 4 | What happens during a Collector outage? | Lambda retries → DLQ → reprocess after recovery |
| 5 | Who governs dual-path (Direct + Collector) during migration? | Defined in migration runbook with clear cutover criteria |

## Platform Contract

### Producer Contract (Lambda / Application)

| Rule | Description |
|------|-------------|
| OTLP only | All producers emit OTLP/HTTP to `http://<collector>:4318/v1/logs` |
| Approved attributes | Use only schema-defined attributes (`service.name`, `event.type`, etc.) |
| No backend awareness | Producers do NOT know which backends receive logs |
| Retry policy | Producers retry on 5xx/timeout, send to DLQ on persistent failure |

### Platform Contract (Collector / Infrastructure)

| Rule | Description |
|------|-------------|
| Collector config | Platform team owns `otel-collector-config.yaml` |
| Routing decisions | Routing rules defined in Collector config, not application code |
| Credential injection | Secrets Manager → environment variables at container start |
| SLA | Collector availability target: 99.9% (health_check monitored) |
| Change management | Config changes require CI validation + staged rollout |

## ONTAP Telemetry Source of Truth

| Telemetry Source | Role | Authority |
|-----------------|------|-----------|
| Raw ONTAP audit logs (EVTX/XML in S3) | Authoritative evidence record | Compliance / Legal |
| EMS / ARP events | Operational and security event signals | Security / Operations |
| FPolicy events | Real-time file activity signals | Security / Investigation |
| OTel Collector | Distribution and routing layer | Platform team |
| Backends (Datadog/Grafana/Honeycomb) | Search, visualization, alerting, investigation | End users |

> **Key principle**: Raw audit logs are the authoritative evidence. OTel-delivered normalized events are operational search and alerting copies. EMS and FPolicy are signals, not complete audit replacements. Backends can differ in retention, indexing, and query semantics.

## ONTAP Telemetry Delivery Options

| Source | Direct Send | OTel Collector | Best For |
|--------|-------------|----------------|----------|
| Audit logs | Simple single backend | Multi-backend / migration | Compliance and investigation |
| EMS / ARP | Fast alerting to one backend | Fan-out to SecOps + SRE | Security and operations |
| FPolicy | Real-time file signal | Multi-backend enrichment | Ransomware triage |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Producer Contract                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ S3 Audit │  │   EMS    │  │ FPolicy  │                      │
│  │  Lambda  │  │  Lambda  │  │  Lambda  │                      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
│       │              │              │                            │
│       └──────────────┼──────────────┘                           │
│                      │ OTLP/HTTP                                │
├──────────────────────┼──────────────────────────────────────────┤
│  Platform Contract   │                                          │
│                      ▼                                          │
│         ┌────────────────────────┐                              │
│         │    OTel Collector      │                              │
│         │  ┌──────────────────┐  │                              │
│         │  │ filter/route/    │  │                              │
│         │  │ redact/batch     │  │                              │
│         │  └──────────────────┘  │                              │
│         └───┬────────┬────────┬──┘                              │
│             │        │        │                                  │
│             ▼        ▼        ▼                                  │
│         Datadog  Grafana  Honeycomb                              │
└─────────────────────────────────────────────────────────────────┘
```
