# Cost Comparison: Direct Send vs OTel Collector Path

## Overview

A cost comparison of two architecture patterns for delivering FSx for ONTAP audit logs to observability backends.

## Pattern Comparison

### Pattern A: Lambda → Vendor API Direct

```
S3 → Lambda → Vendor API (Datadog/Splunk/etc.)
```

### Pattern B: Lambda → OTel Collector → Vendor

```
S3 → Lambda → OTel Collector → Vendor API(s)
```

## Cost Factors

### Pattern A: Direct Send

| Cost Factor | Unit Price (ap-northeast-1) | Monthly Estimate (1M events/month) |
|-------------|----------------------------|-----------------------------------|
| Lambda execution (256MB, avg 500ms) | $0.0000042/100ms | ~$10.50 |
| Lambda requests | $0.20/1M | ~$0.20 |
| S3 GetObject | $0.00037/1000 | ~$0.37 |
| Data transfer (external) | $0.114/GB | ~$1.14 (assuming 1GB) |
| **Total** | | **~$12.21/month** |

### Pattern B: OTel Collector Path

| Cost Factor | Unit Price (ap-northeast-1) | Monthly Estimate (1M events/month) |
|-------------|----------------------------|-----------------------------------|
| Lambda execution (256MB, avg 200ms) | $0.0000042/100ms | ~$4.20 |
| Lambda requests | $0.20/1M | ~$0.20 |
| S3 GetObject | $0.00037/1000 | ~$0.37 |
| ECS Fargate (0.5vCPU, 1GB, 24/7) | — | ~$15.00 |
| NAT Gateway (fixed) | $0.062/hr | ~$45.00 |
| NAT Gateway (data transfer) | $0.062/GB | ~$0.06 (assuming 1GB) |
| **Total** | | **~$64.83/month** |

## Cost Comparison Summary

| Scenario | Pattern A (Direct) | Pattern B (Collector) | Difference |
|----------|-------------------|----------------------|------------|
| 1M events/month | ~$12 | ~$65 | +$53 |
| 10M events/month | ~$105 | ~$80 | -$25 |
| 100M events/month | ~$1,050 | ~$200 | -$850 |

> **Note**: Pattern B has ~$60/month in fixed costs (Fargate + NAT Gateway). As event volume increases, Pattern B becomes more cost-effective.

## When to Use Each Pattern

### Recommended for Pattern A (Direct Send)

- ✅ Single vendor only
- ✅ Low monthly event volume (< 5M)
- ✅ Cost minimization is top priority
- ✅ No VPC required (Lambda runs outside VPC)
- ✅ Prefer simple architecture

### Recommended for Pattern B (OTel Collector)

- ✅ Multi-vendor simultaneous delivery needed
- ✅ Vendor switching is likely
- ✅ High monthly event volume (> 10M)
- ✅ Advanced buffering/retry control needed
- ✅ Vendor lock-in avoidance is important
- ✅ Future integration of metrics/traces planned

## Hidden Cost Considerations

### Pattern A Hidden Costs

- **Vendor switch development cost**: Lambda code rewrite required
- **Multi-vendor Lambda duplication**: Separate Lambda per vendor needed
- **Testing/maintenance cost**: Vendor-specific code grows

### Pattern B Hidden Costs

- **Operational complexity**: Additional Collector monitoring/maintenance
- **NAT Gateway**: Fixed cost for VPC-internal deployment
- **Learning cost**: OTel Collector configuration and operations knowledge

## Cost Optimization Tips

### Reducing Pattern B Costs

1. **No NAT Gateway**: Place Lambda outside VPC, run Collector outside VPC too (Docker on EC2 Spot)
2. **Fargate Spot**: Use for non-critical log processing (up to 70% discount)
3. **Scheduled shutdown**: Stop Collector during nights/weekends in dev/test
4. **ARM64**: Graviton-based Fargate tasks for up to 20% cost reduction

### Reducing Pattern A Costs

1. **No Provisioned Concurrency**: Accept cold starts
2. **ARM64 Lambda**: Graviton-based for up to 20% cost reduction
3. **Batch processing**: Process multiple log files together
