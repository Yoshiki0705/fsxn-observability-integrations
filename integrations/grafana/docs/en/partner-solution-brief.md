# Partner Solution Brief: FSx for ONTAP Observability Quickstart

🌐 [日本語](../ja/partner-solution-brief.md) | **English** (this page)

## Target Users

- FSx for ONTAP users running enterprise file services (NAS consolidation, home directories, shared drives)
- SAP / Oracle / SQL Server / business-critical application workloads on EC2 with FSx for ONTAP storage
- VDI / EUC environments with FSx for ONTAP user profile or data storage
- Organizations needing file access visibility, ransomware-related alerting, or audit compliance
- Organizations evaluating Grafana Cloud as their observability platform

## Problems Addressed

| Pain | How This Solution Helps |
|------|------------------------|
| No visibility into file access patterns | Audit logs shipped to Grafana for investigation |
| Ransomware detection gaps | EMS ARP alerts visible in Grafana with alerting rules |
| Audit compliance requirements | File access evidence in queryable, retained log store |
| EC2-based log collector overhead | Serverless Lambda pipeline — no EC2 to manage |
| Vendor lock-in concerns | OTLP-first design; graduate to Collector for multi-backend |
| Slow incident investigation | Correlated audit + EMS + FPolicy in single dashboard |

## Architecture

```
FSx for ONTAP audit volume → S3 Access Point → EventBridge Scheduler → Lambda → Grafana Cloud OTLP Gateway
ONTAP EMS → Webhook → API Gateway → Lambda → Grafana Cloud
ONTAP FPolicy → ECS Fargate → SQS → Lambda → Grafana Cloud
```

## PoC Scope

| Item | Duration | Deliverable |
|------|----------|-------------|
| Audit log ingestion | Day 1–2 | Logs visible in Grafana Explore |
| EMS alert ingestion | Day 2–3 | EMS events visible, ransomware alert rule active |
| FPolicy ingestion (optional) | Day 3–5 | File operations visible |
| Dashboard and alerts | Day 5–7 | 4-panel dashboard + 3 alert rules |
| Pipeline health alarms | Day 7–8 | CloudWatch alarms configured |
| Go/No-Go report | Day 8–10 | PoC success criteria evaluated |

**Total PoC duration**: 1–2 weeks

## Deliverables

- [ ] Audit log poller deployed and ingesting
- [ ] EMS webhook configured and delivering alerts
- [ ] FPolicy path deployed (if in scope)
- [ ] Grafana dashboard with 4 panels
- [ ] 3 alerting rules (ransomware, quota, failed access)
- [ ] Pipeline health CloudWatch alarms
- [ ] PoC success report with Go/No-Go recommendation

## Production Gaps to Assess

After PoC, evaluate these for production readiness:

| Gap | Decision Needed |
|-----|-----------------|
| Webhook authentication | SHARED_SECRET / API_KEY / IAM |
| Delivery guarantee level | Quickstart (DLQ) vs Medium (SQS buffer) vs Collector |
| Checkpoint model | SSM high-watermark vs DynamoDB object ledger |
| Alloy / Collector graduation | Single-backend direct vs multi-backend pipeline |
| Retention and compliance | Grafana Cloud retention tier vs archive to S3 |
| FPolicy scope | Which volumes/operations to monitor |
| Cost at scale | Validate Cost Model with measured volume |

## Responsibility Split

| Area | Partner / SI | Organization | AWS |
|------|-------------|----------|-----|
| CloudFormation deployment | Lead | Approve | Support |
| ONTAP audit/EMS/FPolicy config | Advise | Execute | — |
| Grafana Cloud setup | Lead | Provide credentials | — |
| Dashboard / alert design | Lead | Review | — |
| Webhook security design | Lead | Approve | Support |
| Production hardening | Lead | Approve + operate | Support |
| Ongoing operations | Handover | Own | Support |

## Related Resources

- [PoC Checklist](poc-checklist.md)
- [Operations Guide](operations.md)
- [Delivery Guarantee Patterns](../../../../docs/en/delivery-guarantees.md)
- [Webhook Security Guide](../../../../docs/en/webhook-security.md)
- [Cost Model](../../../../docs/en/cost-model.md)
