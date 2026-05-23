# Partner Solution Brief: FSx for ONTAP Serverless Observability

## Customer Challenge

Enterprise customers running Amazon FSx for NetApp ONTAP need to ship file access audit logs to their existing SIEM/Observability platform. The current approach requires EC2 instances running syslog-ng and vendor-specific forwarders — adding operational overhead, patching burden, and fixed monthly costs.

**Common customer questions**:
- "How do I get FSx ONTAP audit logs into Splunk/Datadog/Grafana without managing EC2?"
- "Can I detect ransomware activity on my file shares in real-time?"
- "How do I meet compliance requirements for file access auditing?"

## Solution Overview

Serverless log shipping pipeline using Lambda + EventBridge + S3 Access Points. No EC2 instances to manage.

```
FSx ONTAP → S3 Access Point → EventBridge Scheduler → Lambda → Vendor API
                                                                (Datadog/Splunk/Grafana/etc.)
```

**Three event sources** for comprehensive coverage:
1. **Audit Logs** (S3 AP polling): File access events (who accessed what, when)
2. **EMS Webhooks** (API Gateway): System events (ARP ransomware detection, quota alerts)
3. **FPolicy** (ECS Fargate → SQS): Real-time file operation stream (sub-second latency)

## Business Value

| Metric | Before (EC2-based) | After (Serverless) |
|--------|--------------------|--------------------|
| Monthly infrastructure cost | ~$66 (2x t3.medium + EBS) | ~$6 (Lambda + EventBridge) |
| Patching frequency | Monthly (OS + agent) | Zero (managed services) |
| Scaling | Manual (instance resize) | Automatic (Lambda concurrency) |
| Time to first log | Hours (provision + configure) | 30 minutes (CloudFormation deploy) |
| Vendor switching cost | High (rewrite forwarder config) | Low (change Lambda target or use OTel Collector) |

## Target Customer Profiles

### Profile A: Splunk Modernization
- **Current state**: EC2 Universal Forwarder shipping FSx ONTAP logs to Splunk
- **Pain point**: EC2 patching, agent updates, fixed cost
- **Recommended path**: Splunk Serverless integration + EC2 migration guide
- **PoC scope**: Deploy serverless stack in parallel, compare event parity for 48h

### Profile B: New Observability Platform
- **Current state**: FSx ONTAP audit logs not shipped anywhere
- **Pain point**: No visibility into file access patterns, compliance gaps
- **Recommended path**: Start with free-tier vendor (New Relic 100GB/month or Grafana 50GB/month)
- **PoC scope**: Deploy audit poller, confirm logs queryable, build first dashboard

### Profile C: Multi-Vendor / Vendor-Neutral
- **Current state**: Multiple observability tools across teams
- **Pain point**: Duplicate pipelines, vendor lock-in
- **Recommended path**: OTel Collector (single Lambda, fan-out to multiple backends)
- **PoC scope**: Local Docker validation (5 min), then AWS deployment with 2+ backends

### Profile D: Security / Ransomware Detection
- **Current state**: No real-time alerting on file system anomalies
- **Pain point**: Ransomware detection relies on periodic scans
- **Recommended path**: EMS webhook (ARP events) + FPolicy (file operation stream)
- **PoC scope**: Simulate ARP trigger, confirm alert in <30 seconds

## PoC Engagement Model

### Scope (1-week engagement)

| Day | Activity | Deliverable |
|-----|----------|-------------|
| 1 | Requirements gathering + environment assessment | PoC Plan document |
| 2 | Deploy prerequisites (S3 AP, audit logging) | Working S3 AP + audit logs flowing |
| 3 | Deploy vendor integration + validate delivery | First log in backend |
| 4 | Dashboard + alerts + operational validation | Dashboard screenshot + DLQ empty |
| 5 | Documentation + Go/No-Go decision | PoC Report + Next Steps |

### Success Criteria (Level 1 — Minimum)

- [ ] One audit log record arrives in the observability backend
- [ ] SSM checkpoint advances after successful delivery
- [ ] DLQ remains empty (zero failed deliveries)
- [ ] CloudFormation deploy and delete complete cleanly
- [ ] Cost estimate produced for expected production volume

### Go/No-Go Decision Inputs

| Question | Owner |
|----------|-------|
| Does delivery latency meet requirements? | Platform team |
| Is the cost acceptable for production volume? | Finance / FinOps |
| Does the data classification allow external delivery? | Security / Compliance |
| Who owns the pipeline operationally? | Operations |
| Is the vendor's data residency acceptable? | Legal / DPO |

## Pricing Guidance

### AWS Infrastructure (all vendors)

| Log Volume | Monthly AWS Cost | Notes |
|-----------|-----------------|-------|
| 1 GB/month | ~$2 | Lambda + EventBridge + Secrets Manager |
| 10 GB/month | ~$8 | Typical enterprise file server |
| 100 GB/month | ~$41 | Large-scale deployment |

### Vendor Platform Costs (varies)

See [Vendor Comparison](vendor-comparison.md) for detailed cost tables per vendor.

**Free tier options for PoC**:
- New Relic: 100 GB/month (best for PoC)
- Grafana Cloud: 50 GB/month
- Sumo Logic: 500 MB/day (~15 GB/month)
- Honeycomb: 20M events/month

## Differentiation

| vs. | This Solution | Alternative |
|-----|--------------|-------------|
| EC2-based (AWS Blog) | Zero EC2, pay-per-use, auto-scaling | Fixed cost, patching required |
| CloudWatch Logs only | Multi-vendor, rich query, dashboards | Limited to CloudWatch ecosystem |
| Third-party agents | No agent on FSx, S3 AP native | Agent compatibility issues |
| Manual log download | Automated, real-time, alerting | Manual, delayed, no alerting |

## Resources

- [GitHub Repository](https://github.com/Yoshiki0705/fsxn-observability-integrations)
- [PoC Success Criteria](poc-success-criteria.md)
- [Vendor Comparison](vendor-comparison.md)
- [Security Best Practices](security-best-practices.md)
- [Demo Scenarios](demo-scenarios.md)

## Next Steps for Partners

1. Identify a customer with FSx for ONTAP + observability need
2. Use this Solution Brief in the initial conversation
3. Propose a 1-week PoC engagement using the model above
4. Deploy using the CloudFormation templates (30-minute Quick Start)
5. Deliver PoC Report with Go/No-Go recommendation
