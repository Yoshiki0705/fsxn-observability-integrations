# Cost Model — Direct Send vs Collector vs Firehose

## Cost Model Inputs

To estimate monthly cost for your deployment, gather these values:

| Input | How to Measure | Example |
|-------|---------------|---------|
| Audit files per hour | `aws s3 ls` on S3 AP over 1 hour | 50 files/hour |
| Average file size | Sample 100 files | 200 KB |
| Records per file | Parse sample files | 500 records |
| Lambda duration per file | CloudWatch `Duration` metric | 800 ms |
| Schedule interval | CloudFormation parameter | 5 minutes |
| Grafana ingest volume | files/hour × avg size | ~10 MB/hour |
| Grafana retention tier | Grafana Cloud plan | 30 days |
| CloudTrail data events (if enabled) | CloudTrail event count | $0.10 / 100K events |
| Collector compute (if used) | ECS Fargate vCPU-hours | 0.25 vCPU |
| NAT Gateway (if VPC Lambda) | Data processed | $0.045/GB |

## Path Comparison

| Path | Fixed Cost | Variable Cost | Best For |
|------|-----------|---------------|----------|
| **Direct send** (Part 6) | ~$0 | Lambda invocations + duration + Grafana ingest | Low-medium volume, single backend |
| **OTel Collector** (Part 5) | Fargate/EC2 compute | Lambda + Collector + multi-backend ingest | Multi-backend, enrichment, redaction |
| **Firehose** (Splunk/Datadog) | ~$0 | Firehose ingestion ($0.029/GB) + vendor ingest | High volume with built-in Firehose destination |

## Direct Send Cost Estimate (Example)

Assumptions: 50 files/hour, 200 KB avg, 5-min polling, ap-northeast-1

| Component | Calculation | Monthly Cost |
|-----------|-------------|-------------|
| Lambda invocations | 12/hour × 720 hours = 8,640 | ~$0.02 |
| Lambda duration | 8,640 × 4s avg × 256 MB | ~$0.15 |
| SSM Parameter Store | Standard tier, free | $0.00 |
| EventBridge Scheduler | Free tier covers | $0.00 |
| SQS (DLQ) | Minimal messages | ~$0.00 |
| Secrets Manager | 1 secret × $0.40/month | $0.40 |
| Grafana Cloud ingest | 50 × 200KB × 720h = ~7 GB/month | Plan-dependent |
| **Total AWS cost** | | **~$0.57/month** |

> Grafana Cloud ingest cost depends on your plan tier. Free tier includes 50 GB/month of logs.

## When Direct Send Becomes Expensive

Direct send cost scales linearly with volume. Consider alternatives when:

- Lambda duration exceeds 80% of schedule interval (throughput ceiling)
- Grafana ingest exceeds plan allocation (overage charges)
- Retry/duplicate delivery adds significant ingest overhead
- Multiple backends needed (Collector amortizes compute across destinations)

## Collector Path Cost Estimate (Example)

Assumptions: Same volume, ECS Fargate 0.25 vCPU / 0.5 GB

| Component | Calculation | Monthly Cost |
|-----------|-------------|-------------|
| Lambda (reader) | Same as above | ~$0.17 |
| Fargate Collector | 0.25 vCPU × 720h × $0.04048 + 0.5 GB × 720h × $0.004445 | ~$8.90 |
| Multi-backend ingest | Grafana + Datadog + archive | Plan-dependent |
| **Total AWS cost** | | **~$9.07/month** |

The Collector path has higher fixed cost but enables multi-backend delivery, enrichment, and persistent queueing without additional Lambda complexity.

## Cost Optimization Tips

- Use `rate(5 minutes)` or longer for non-urgent audit visibility
- Set `MAX_KEYS_PER_RUN` to match your Lambda memory/timeout budget
- Monitor Lambda `Duration` p95 — right-size memory allocation
- Use Grafana Cloud log retention tiers appropriate to your compliance needs
- Avoid CloudTrail data events unless near-real-time trigger is required ($0.10/100K events)
- Deploy Lambda outside VPC to avoid NAT Gateway cost for S3 AP access


## NetApp-Specific Cost Drivers

For FSx for ONTAP environments, these additional factors affect pipeline cost:

| Driver | Impact | How to Control |
|--------|--------|----------------|
| Audit log rotation interval | More frequent rotation = more files per poll = higher Lambda duration | Tune rotation interval in ONTAP audit config |
| Average audit file size | Larger files = longer parse time per invocation | Adjust MAX_KEYS_PER_RUN accordingly |
| FPolicy event volume | High-volume shares can generate thousands of events/second | Scope FPolicy by volume/path/operation type |
| EMS event volume | Typically low; spikes during incidents | No action needed for cost |
| FSx provisioned throughput | S3 AP read throughput is bounded by FSx file system throughput | Monitor read latency; scale FSx if needed |
| Grafana ingest GB/day | Primary ongoing cost for Grafana Cloud | Control via polling interval + MAX_KEYS_PER_RUN |
| CloudTrail data events (if enabled) | $0.10 / 100K events; can be significant at scale | Use polling pattern instead (default) |
| NAT Gateway (if VPC Lambda) | $0.045/GB processed | Deploy Lambda outside VPC for S3 AP access |

### FPolicy Volume Estimation

FPolicy event volume depends on workload:

| Workload Type | Typical Event Rate | Recommendation |
|---------------|-------------------|----------------|
| Home directories (low activity) | 10-100 events/min | Full monitoring feasible |
| Shared file server (medium) | 100-1000 events/min | Scope to security-relevant operations |
| Build/CI output (high I/O) | 1000+ events/min | Scope narrowly or use audit logs instead |
| Database files on NAS | Very high open/read/write | Exclude from FPolicy scope |
