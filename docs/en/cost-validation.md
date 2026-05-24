# Cost Validation: Estimated vs Actual

## Purpose

This document tracks the comparison between estimated costs (from vendor READMEs and the cost model) and actual AWS billing data after production deployment. Use this to validate cost assumptions and refine estimates for future deployments.

> **Status**: Template — populate with actual billing data after 1 month of production operation.

## Methodology

1. Deploy a single vendor integration for 30 days
2. Record actual AWS costs from Cost Explorer (filter by stack tags)
3. Record actual vendor costs from vendor billing
4. Compare with estimates from the vendor README

## Cost Estimate (from documentation)

### AWS Infrastructure (per vendor integration)

| Component | Estimated Monthly Cost | Assumptions |
|-----------|----------------------|-------------|
| Lambda (audit poller) | ~$3 | 5-min schedule, 256 MB, ~30s avg duration |
| EventBridge Scheduler | ~$1 | 8,640 invocations/month |
| Secrets Manager | ~$0.40 | 1 secret, ~8,640 API calls/month |
| SSM Parameter Store | ~$0 | Free tier (standard parameters) |
| SQS (DLQ) | ~$0 | Minimal messages (healthy state) |
| CloudWatch Logs | ~$1-3 | Depends on log level |
| **Total AWS** | **~$5-8** | — |

### Vendor Platform (10 GB/month audit logs)

| Vendor | Estimated Monthly Cost | Tier |
|--------|----------------------|------|
| Sumo Logic | $0 | Free (500 MB/day) |
| Honeycomb | $0 | Free (20M events/month) |
| New Relic | $0 | Free (100 GB/month) |
| Datadog | ~$15 | Logs indexed (15-day retention) |
| Grafana Cloud | ~$50 | Pro plan |
| Elastic Cloud | ~$95 | Standard |
| Dynatrace | ~$25 | DDU-based |
| Splunk Cloud | ~$150+ | Volume-based |

## Actual Cost (populate after 30 days)

### AWS Infrastructure — Actual

| Component | Actual Monthly Cost | Delta vs Estimate | Notes |
|-----------|--------------------|--------------------|-------|
| Lambda | $ ___ | ___ | Duration: ___s avg |
| EventBridge Scheduler | $ ___ | ___ | Invocations: ___ |
| Secrets Manager | $ ___ | ___ | API calls: ___ |
| CloudWatch Logs | $ ___ | ___ | GB ingested: ___ |
| SQS | $ ___ | ___ | Messages: ___ |
| **Total AWS** | **$ ___** | **___** | — |

### Vendor Platform — Actual

| Vendor | Actual Monthly Cost | Delta vs Estimate | Notes |
|--------|--------------------|--------------------|-------|
| ___ | $ ___ | ___ | Volume: ___ GB |

## Measurement Commands

```bash
# Get Lambda cost for the last 30 days
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-06-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --filter '{
    "And": [
      {"Dimensions": {"Key": "SERVICE", "Values": ["AWS Lambda"]}},
      {"Tags": {"Key": "aws:cloudformation:stack-name", "Values": ["fsxn-*"]}}
    ]
  }' \
  --region ap-northeast-1

# Get all costs tagged with fsxn stacks
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-06-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --filter '{
    "Tags": {"Key": "aws:cloudformation:stack-name", "Values": ["fsxn-*"]}
  }' \
  --region ap-northeast-1
```

## Cost Optimization Findings

After validation, document any findings:

| Finding | Impact | Recommendation |
|---------|--------|---------------|
| ___ | $ ___/month | ___ |

## Comparison Summary

| Category | Estimated | Actual | Accuracy |
|----------|-----------|--------|----------|
| AWS Infrastructure | $5-8 | $ ___ | ___% |
| Vendor Platform | $ ___ | $ ___ | ___% |
| **Total** | **$ ___** | **$ ___** | **___%** |

## Lessons for Future Estimates

- [ ] Lambda duration assumption accurate?
- [ ] Log volume assumption accurate?
- [ ] Vendor pricing tier assumption accurate?
- [ ] Any unexpected costs (data transfer, CloudWatch, etc.)?

## Related Documents

- [Cost Model](cost-model.md)
- [Pipeline SLO](pipeline-slo.md)
- [Vendor Comparison](vendor-comparison.md)
