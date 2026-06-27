# Partner FAQ: FSx for ONTAP Observability Integrations

## For Partner SAs and Delivery Teams

Common questions from customer conversations, with recommended answers.

---

## Architecture & Positioning

### Q: How is this different from the existing AWS Blog (Splunk + EC2)?

**A**: The [existing AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/) uses two EC2 instances (syslog-ng + Universal Forwarder). Our approach replaces that with serverless Lambda functions — same audit data, same query capabilities, 90% cost reduction, zero OS patching.

| Aspect | EC2 Blog Pattern | This Project |
|--------|-----------------|--------------|
| Infrastructure | 2x EC2 (always-on) | Lambda (pay-per-use) |
| Monthly cost | ~$66 | ~$6 |
| OS patching | Required | None |
| Scaling | Manual | Automatic |
| Vendor support | Splunk only | 9 vendors |

### Q: Does this require changes to FSx for ONTAP configuration?

**A**: Minimal. You need:
1. Audit logging enabled on the SVM (`vserver audit create`)
2. An S3 Access Point created for the FSx file system

No changes to NFS/SMB data paths, no performance impact on production workloads, no additional ONTAP licenses.

### Q: Can this work with an existing FSx for ONTAP deployment?

**A**: Yes. The integration reads audit logs through the S3 Access Point — it's a read-only, non-intrusive addition. No changes to existing file shares, permissions, or data paths.

### Q: What about FPolicy? Doesn't that impact performance?

**A**: FPolicy is optional and separate from the audit log path. The audit log poller (primary path) has zero impact on file operations. FPolicy adds real-time file operation visibility but should be evaluated for performance impact in high-IOPS environments. Start with audit logs only.

---

## Customer Fit

### Q: Which customers should I propose this to?

**A**: Best fit:
- Already using FSx for ONTAP (or planning to migrate)
- Have an existing observability platform (any of the 9 supported vendors)
- Need audit log visibility for compliance, security, or operations
- Want to reduce EC2-based collector infrastructure

Specific scenarios:
- Enterprise file shares (department servers, shared drives)
- SAP/Oracle/SQL Server with FSx for ONTAP storage
- VDI/EUC home directories
- Design/engineering repositories
- Compliance-driven audit requirements (FISC, ISMAP, J-SOX)

### Q: What if the customer doesn't have FSx for ONTAP yet?

**A**: Two options:
1. **Sample data mode**: Deploy with synthetic audit logs to demonstrate the pipeline and vendor integration
2. **Full PoC**: Include FSx for ONTAP provisioning in the PoC scope (adds 1-2 days)

### Q: What's the minimum viable PoC?

**A**: 30 minutes to first log in the vendor platform:
1. Deploy CloudFormation template (5 min)
2. Upload sample audit data (5 min)
3. Trigger Lambda manually (1 min)
4. Query in vendor platform (5 min)
5. Verify checkpoint + DLQ health (5 min)

---

## Technical Questions

### Q: Why polling instead of event-driven (S3 notifications)?

**A**: FSx for ONTAP S3 Access Points do not support S3 Event Notifications or EventBridge object-level events. This is a platform constraint, not a design choice. The polling pattern (EventBridge Scheduler every 5 minutes) is the recommended approach. CloudTrail data events are a documented alternative for near-real-time needs.

### Q: What's the delivery latency?

**A**:
- Audit logs: < 10 minutes (5-min schedule + processing)
- EMS webhooks: < 5 seconds (real-time)
- FPolicy: < 30 seconds (near-real-time via SQS)

### Q: What happens if the vendor API is down?

**A**:
- Lambda retries with exponential backoff (3 attempts)
- Failed invocations land in the DLQ (preserved 14 days)
- Next scheduled run retries from the checkpoint automatically
- No data loss — audit files remain on FSx for ONTAP

### Q: Is this production-ready?

**A**: The project defines 4 Production Readiness Levels. The Quick Start (Level 1) is suitable for PoC. For production, progress through Level 2 (dashboards + alerts) and Level 3 (DynamoDB ledger + security review). See the Pipeline SLO document for Go/No-Go criteria.

### Q: What about data residency / cross-border transfer?

**A**: Depends on the vendor:
- **JP region available**: Sumo Logic (JP), Elastic (Tokyo), Dynatrace (region-specific)
- **Self-hosted option**: Elastic, Splunk (data stays in your VPC)
- **US only**: Honeycomb
- **Multi-region**: Datadog (US/EU/AP1-Tokyo), New Relic (US/EU, JP planned July 2026), Grafana Cloud (US/EU/AU)

See the Data Residency Matrix for details.

---

## Commercial & Licensing

### Q: What does this cost?

**A**: Two components:
1. **AWS infrastructure**: ~$5-10/month (Lambda + EventBridge + Secrets Manager)
2. **Vendor platform**: Varies (some have generous free tiers)

Free tier options:
- Sumo Logic: 1.25 credits/day free (7-day retention)
- Honeycomb: 20M events/month free
- New Relic: 100 GB/month free
- Datadog: 14-day trial
- Elastic: 14-day trial

### Q: Is there a license for this project?

**A**: MIT license. Free to use, modify, and distribute. No attribution required in production deployments.

### Q: Can we white-label this for customer delivery?

**A**: Yes (MIT license). You can fork, customize, and deliver under your own branding. We recommend maintaining a link back to the upstream repository for updates.

---

## Delivery & Support

### Q: How long does a typical PoC take?

**A**:
- **Quick validation**: 30 minutes (sample data, single vendor)
- **Full PoC with real data**: 1-2 weeks (includes FSx audit setup, vendor configuration, dashboard creation, SLO validation)
- **Production deployment**: 2-4 weeks (adds security review, runbook testing, Go/No-Go)

### Q: What's the handoff to the customer?

**A**: Deliverables:
1. Deployed CloudFormation stacks (customer-owned)
2. Operational runbooks (DLQ replay, Lambda errors, checkpoint staleness)
3. Pipeline SLO document (customized thresholds)
4. Dashboard + alert configuration
5. Go/No-Go checklist (signed off)

### Q: What if the customer wants a vendor we don't support?

**A**: The architecture is vendor-agnostic. Adding a new vendor requires:
1. A Lambda handler (~200 lines of Python)
2. A CloudFormation template (copy from existing)
3. Vendor API documentation

Typical effort: 1-2 days for a new vendor integration.

---

## Workshop Delivery

### Q: Can I run a workshop without AWS SA support?

**A**: Yes. The Workshop Hands-On Guide is self-contained:
- 3.5 hours, 6 modules
- Step-by-step commands
- Sample data mode (no FSx for ONTAP required)
- Facilitator notes with common issues

### Q: What do participants need?

**A**:
- AWS account with admin access (sandbox)
- Vendor account (free tier)
- AWS CLI v2
- 3.5 hours of focused time

---

## Related Documents

- [Partner Solution Brief](partner-solution-brief.md)
- [PoC Proposal Template](poc-proposal-template.md)
- [Workshop Hands-On Guide](workshop-hands-on-half-day.md)
- [Pipeline SLO](pipeline-slo.md)
- [Data Classification Guide](data-classification.md)
- [Vendor Comparison](vendor-comparison.md)
