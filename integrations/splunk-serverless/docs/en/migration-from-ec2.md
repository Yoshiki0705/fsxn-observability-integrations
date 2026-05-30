# Migration Guide: EC2-Based Splunk to Serverless

## Overview

This guide helps you migrate from the [EC2-based Splunk integration](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/) (syslog-ng + Universal Forwarder) to the serverless Lambda + HEC pattern.

## Architecture Comparison

```
[Before: EC2-based]
FSx for ONTAP → syslog-ng (EC2) → Splunk Universal Forwarder (EC2) → Splunk Enterprise/Cloud
  - 2 EC2 instances to manage
  - OS patching, agent updates required
  - Fixed cost regardless of log volume

[After: Serverless]
FSx for ONTAP → S3 Access Point → EventBridge Scheduler → Lambda → Splunk HEC
  - Zero EC2 instances
  - No patching, no agent management
  - Pay-per-use (scales to zero)
```

## Migration Checklist

### Phase 1: Preparation (Day 1)

- [ ] Verify current Splunk index and sourcetype configuration
- [ ] Document current syslog-ng filter rules (what events are forwarded)
- [ ] Confirm Splunk HEC is enabled and accessible
- [ ] Create a new HEC token for the serverless integration
- [ ] Verify FSx for ONTAP audit logging is writing to S3 (via S3 Access Point)
- [ ] Identify any custom field extractions or transforms in the UF

### Phase 2: Parallel Deployment (Day 2-3)

- [ ] Deploy the serverless stack alongside the existing EC2 pipeline
- [ ] Use a **separate Splunk index** (e.g., `fsxn_audit_serverless`) for validation
- [ ] Compare events between old and new pipelines for 24-48 hours
- [ ] Verify field mapping parity (sourcetype, host, source fields)
- [ ] Confirm no data loss (event count comparison)

### Phase 3: Cutover (Day 4-5)

- [ ] Switch the serverless stack to the production index (`fsxn_audit`)
- [ ] Disable the syslog-ng to UF pipeline (stop services, don't terminate yet)
- [ ] Monitor for 24 hours with both EC2 instances stopped but not terminated
- [ ] Verify dashboards and alerts continue to function

### Phase 4: Cleanup (Day 7+)

- [ ] Terminate EC2 instances (syslog-ng + UF)
- [ ] Remove associated security groups, IAM roles, EBS volumes
- [ ] Update documentation and runbooks
- [ ] Archive old CloudFormation/Terraform resources

## Field Mapping

| EC2 UF Field | Serverless Equivalent | Notes |
|-------------|----------------------|-------|
| `host` | SVM name (from audit log) | Previously the EC2 hostname |
| `source` | `fsxn-observability` | Previously syslog path |
| `sourcetype` | `fsxn:ontap:audit` | Same (configurable) |
| `index` | `fsxn_audit` | Same (configurable) |
| `_time` | Event timestamp from audit log | Previously syslog timestamp |

## What Changes for Splunk Users

### Unchanged
- Index name and sourcetype (configurable to match existing)
- Search queries (SPL) with same field names
- Dashboards and saved searches
- Alert rules

### Changed
- `host` field: was EC2 hostname, now SVM name
- `source` field: was syslog file path, now `fsxn-observability`
- Delivery latency: was near-real-time (syslog), now polling interval (default 5 min)
- No syslog metadata (facility, severity) — use ONTAP event fields instead

## Cost Comparison

| Component | EC2-Based (monthly) | Serverless (monthly) |
|-----------|--------------------|--------------------|
| EC2 instances (2x t3.medium) | ~$60 | $0 |
| EBS volumes (2x 20GB) | ~$6 | $0 |
| Lambda | $0 | ~$5 (10 GB/month) |
| EventBridge Scheduler | $0 | ~$0.01 |
| Secrets Manager | $0 | ~$0.40 |
| **Total** | **~$66** | **~$6** |

> Savings: ~$60/month (~90% reduction) for typical audit log volumes.

## Rollback Plan

If issues are discovered after cutover:

1. Start the stopped EC2 instances (syslog-ng + UF)
2. Verify syslog-ng is receiving events from FSx for ONTAP
3. Delete the serverless CloudFormation stack
4. Investigate and resolve issues before re-attempting migration

## FAQ

**Q: Can I run both pipelines simultaneously?**
A: Yes. Use separate Splunk indexes during validation. Both can read from the same FSx for ONTAP audit logs without conflict.

**Q: Will I lose events during cutover?**
A: No. The serverless Lambda uses checkpointing — it will process all audit log files from the last checkpoint forward. There may be brief duplicate events during the overlap period.

**Q: What about near-real-time requirements?**
A: The default polling interval is 5 minutes. For near-real-time needs, consider the FPolicy path (sub-second latency) or reduce the polling interval to 1 minute.

**Q: Do I need to change my Splunk dashboards?**
A: Typically no. If your dashboards filter on `host=<ec2-hostname>`, update to `host=<svm-name>` or remove the host filter.
