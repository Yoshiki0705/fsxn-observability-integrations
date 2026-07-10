# Cost Model: OTel Collector Integration

🌐 [日本語](../ja/cost-model.md) | **English** (this page)

## Cost Formula

```
Monthly Cost = event_volume × destination_count × retention_policy
             + infrastructure_cost (Lambda + Collector + Network)
```

## Cost Drivers

| Driver | Component | Scaling Factor |
|--------|-----------|----------------|
| Lambda execution | Per-invocation + duration | Event volume |
| Collector compute | ECS Fargate (vCPU + memory) | Throughput |
| NAT Gateway | Per-hour + per-GB processed | Egress volume |
| VPC Endpoints | Per-hour + per-GB processed | API call volume |
| CloudWatch Logs | Ingestion + storage | Log verbosity |
| Backend ingest | Per-GB ingested | Event volume × destinations |
| Backend retention | Per-GB stored/day | Retention period |
| Data transfer | Cross-AZ + internet egress | Event volume |

## Sample Event Size Estimation

| Event Type | Avg Size (JSON) | Avg Size (OTLP) | Notes |
|------------|-----------------|------------------|-------|
| S3 Audit (single) | ~1.5 KB | ~1.2 KB | File operation event |
| EMS event | ~2.0 KB | ~1.6 KB | System event |
| FPolicy event | ~1.0 KB | ~0.8 KB | File access notification |
| Batch (100 events) | ~150 KB | ~80 KB | OTLP batching is more efficient |

## Events/Day Examples

| Volume Tier | Events/Day | GB/Day (OTLP) | Use Case |
|-------------|-----------|----------------|----------|
| **Low** | 10,000 | ~0.01 GB | Dev/test environment, single SVM |
| **Medium** | 500,000 | ~0.5 GB | Production, moderate file activity |
| **High** | 5,000,000 | ~5 GB | High-activity production, multiple SVMs |
| **Very High** | 50,000,000 | ~50 GB | Enterprise, heavy NAS workloads |

## Backend Ingest GB/Day Estimate

```
ingest_gb_per_day = events_per_day × avg_event_size_bytes / (1024³)
                  × destination_count
```

| Volume | 1 Backend | 2 Backends | 3 Backends |
|--------|-----------|------------|------------|
| Low (10K/day) | 0.01 GB | 0.02 GB | 0.03 GB |
| Medium (500K/day) | 0.5 GB | 1.0 GB | 1.5 GB |
| High (5M/day) | 5 GB | 10 GB | 15 GB |
| Very High (50M/day) | 50 GB | 100 GB | 150 GB |

## NAT Gateway vs VPC Endpoint Cost Tradeoff

### NAT Gateway

| Component | Cost (ap-northeast-1) | Notes |
|-----------|----------------------|-------|
| Hourly charge | $0.062/hour (~$45/month) | Per NAT Gateway |
| Data processing | $0.062/GB | All traffic through NAT |

### VPC Endpoint (Interface)

| Component | Cost (ap-northeast-1) | Notes |
|-----------|----------------------|-------|
| Hourly charge | $0.014/hour (~$10/month) | Per endpoint per AZ |
| Data processing | $0.01/GB | Traffic through endpoint |

### Decision Matrix

| Scenario | Recommendation | Reason |
|----------|---------------|--------|
| < 100 GB/month egress | NAT Gateway | Simpler, single component |
| > 100 GB/month egress | VPC Endpoint | Lower per-GB cost |
| Multiple AWS services | VPC Endpoints | Per-service isolation |
| Backend is AWS service | VPC Endpoint | No internet egress needed |
| Backend is external SaaS | NAT Gateway | Must reach internet |

## CloudWatch Logs Retention Impact

| Retention | Storage Cost/GB/month | 30-day cost (1 GB/day ingest) |
|-----------|----------------------|-------------------------------|
| 1 day | $0.033 | $1.00 |
| 7 days | $0.033 | $7.00 |
| 14 days | $0.033 | $14.00 |
| 30 days | $0.033 | $30.00 |
| 90 days | $0.033 | $90.00 |
| Never expire | $0.033 | Grows indefinitely |

**Recommendation**: Set Lambda log retention to 14-30 days. Set Collector log retention to 7-14 days.

## Noisy Operation Filtering Savings

### Before Filtering (all events to all backends)

```
5M events/day × 3 backends × $0.50/GB ingest = $7.50/day = $225/month
```

### After Filtering (route by type)

| Event Type | Volume | Destination | Cost |
|------------|--------|-------------|------|
| Security (delete/perm) | 50K/day | SIEM + Grafana + Archive | $0.15/day |
| Read events | 4M/day | Archive only (cheap) | $0.40/day |
| Other operations | 950K/day | Grafana + Honeycomb | $1.90/day |

```
Total after filtering: $2.45/day = $73.50/month (67% savings)
```

## High-Volume Read Event Strategy

Read events (GetObject, ReadDir, ListDir) typically account for 60-80% of total event volume but have low security value.

### Options

| Strategy | Cost Impact | Data Loss | Use Case |
|----------|-------------|-----------|----------|
| Drop entirely | -80% volume | Yes | Non-compliance environments |
| Sample (1:100) | -79% volume | Partial | Trend analysis sufficient |
| Route to cheap storage | -60% cost | No | Compliance requires retention |
| Shorter retention (7d) | -50% cost | After 7d | Operational troubleshooting only |

### Collector Config for Read Event Routing

```yaml
# Route read events to cheap storage, security events to SIEM
connectors:
  routing:
    default_pipelines: [logs/general]
    table:
      - statement: route() where attributes["fsxn.operation"] == "READ"
        pipelines: [logs/cheap]
      - statement: route() where attributes["fsxn.operation"] == "DELETE"
        pipelines: [logs/security]

service:
  pipelines:
    logs/input:
      receivers: [otlp]
      processors: [batch]
      exporters: [routing]
    logs/general:
      receivers: [routing]
      exporters: [otlp_http/grafana, otlp_http/honeycomb]
    logs/cheap:
      receivers: [routing]
      exporters: [otlp_http/archive]
    logs/security:
      receivers: [routing]
      exporters: [otlp_http/siem, otlp_http/grafana, otlp_http/archive]
```

## Monthly Cost Estimate Summary

### Low Volume (10K events/day, 1 backend)

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (256MB, 500ms avg) | ~$0.50 |
| ECS Fargate (0.25 vCPU, 512MB) | ~$9.00 |
| NAT Gateway (hourly) | ~$45.00 |
| NAT Gateway (data, 0.3 GB) | ~$0.02 |
| CloudWatch Logs (14d retention) | ~$0.50 |
| Backend ingest (Grafana, 0.3 GB) | ~$1.50 |
| **Total** | **~$56.52** |

### Medium Volume (500K events/day, 2 backends)

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (512MB, 800ms avg) | ~$15.00 |
| ECS Fargate (0.5 vCPU, 1GB) | ~$18.00 |
| NAT Gateway (hourly) | ~$45.00 |
| NAT Gateway (data, 30 GB) | ~$1.86 |
| CloudWatch Logs (14d retention) | ~$7.00 |
| Backend ingest (2×, 30 GB) | ~$150.00 |
| **Total** | **~$236.86** |

### High Volume (5M events/day, 3 backends, with filtering)

| Component | Monthly Cost |
|-----------|-------------|
| Lambda (1024MB, 1s avg) | ~$75.00 |
| ECS Fargate (1 vCPU, 2GB, 2 tasks) | ~$72.00 |
| NAT Gateway (hourly) | ~$45.00 |
| NAT Gateway (data, 150 GB) | ~$9.30 |
| CloudWatch Logs (7d retention) | ~$5.00 |
| Backend ingest (filtered, 73.5 GB) | ~$367.50 |
| **Total** | **~$573.80** |

> **Note**: Backend ingest costs vary significantly by vendor. Check your vendor's pricing page for accurate estimates. The $5/GB used above is illustrative.
