# Vendor Comparison

## Supported Vendors

| Vendor | Delivery Method | Auth Method | Max Batch Size | Firehose Support |
|--------|----------------|-------------|----------------|-----------------|
| Datadog | Logs API v2 | API Key (Header) | 5MB/request | ✅ |
| New Relic | Log API | License Key (Header) | 1MB/request | ✅ |
| Grafana Cloud | OTLP Gateway | Basic Auth | No limit (4MB recommended) | ❌ |
| Splunk | HEC | HEC Token (Header) | No limit | ✅ (Built-in) |
| CrowdStrike Falcon LogScale | HEC (Splunk-compatible) | Bearer Token (Ingest Token) | No limit | ❌ |
| Elastic | Bulk API | API Key / Basic Auth | No limit (10MB recommended) | ❌ |
| Dynatrace | Log Ingest API | API Token (Header) | 1MB/request | ✅ |
| Sumo Logic | HTTP Source | Embedded in URL | 1MB/request | ❌ |
| Honeycomb | Events API | API Key (Header) | 5MB/request | ❌ |
| OTel Collector | OTLP/HTTP | Configurable | Configurable | ❌ |

## Cost Comparison

Estimated monthly costs for the **observability platform ingestion** (excludes AWS infrastructure costs which are ~$5-50/month depending on volume):

| Vendor | Free Tier | 1 GB/month | 10 GB/month | 100 GB/month | Pricing Model |
|--------|-----------|-----------|------------|-------------|---------------|
| New Relic | 100 GB/month | $0 | $0 | $0 | Per-GB beyond free tier ($0.35/GB) |
| Grafana Cloud | 50 GB/month | $0 | $0 | ~$40 | Per-GB beyond free tier ($0.50/GB) |
| Sumo Logic | 500 MB/day (~15 GB/month) | $0 | $0 | ~$300 | Per-GB/day tier-based |
| Honeycomb | 20M events/month | $0 | $0 | ~$100 | Per-event based |
| Datadog | None (trial only) | ~$10 | ~$100 | ~$1,000 | $0.10/GB ingested + retention |
| Splunk | None (license-based) | License-dependent | License-dependent | License-dependent | Daily indexing volume license |
| Dynatrace | None (DDU-based) | ~$1 DDU/day | ~$10 DDU/day | ~$100 DDU/day | Davis Data Units |
| Elastic Cloud | 14-day trial | ~$30 (min deployment) | ~$95 | ~$300+ | Storage + compute |
| CrowdStrike Falcon LogScale | Community: 1 GB/day | $0 | License-dependent | License-dependent | Per-GB/day or Falcon bundle |
| OTel Collector | N/A (self-hosted) | $0 (infra only) | $0 (infra only) | $0 (infra only) | Backend cost only |

> **Note**: Prices are approximate and may vary by region, contract, and commitment. Always verify with the vendor's current pricing page. AWS infrastructure costs (Lambda, EventBridge, S3, Secrets Manager) are typically $5-50/month for most audit log volumes.

### AWS Infrastructure Cost Estimate

| Component | 1 GB/month | 10 GB/month | 100 GB/month |
|-----------|-----------|------------|-------------|
| Lambda (256MB, 5min interval) | ~$1 | ~$5 | ~$30 |
| EventBridge Scheduler | ~$0.01 | ~$0.01 | ~$0.01 |
| Secrets Manager | ~$0.40 | ~$0.40 | ~$0.40 |
| CloudWatch Logs | ~$0.50 | ~$2 | ~$10 |
| SQS (DLQ) | ~$0 | ~$0 | ~$0 |
| **Total AWS** | **~$2** | **~$8** | **~$41** |

## Selection Guide

### Cost-Focused
- **New Relic**: Most generous free tier (100 GB/month)
- **Grafana Cloud**: Good free tier (50 GB/month) + OSS ecosystem
- **Sumo Logic**: Free tier available (500 MB/day)
- **Elastic**: Self-hosted option (no ingestion cost)

### Existing Environment Integration
- **Datadog**: Already using Datadog for APM/infrastructure
- **Splunk**: Existing Splunk environment (serverless migration from EC2 UF)
- **Dynatrace**: Want AI-powered root cause analysis with APM correlation

### Vendor Lock-in Avoidance
- **OTel Collector**: Vendor-neutral, switch backends without code changes
- **Grafana Cloud**: OSS-based stack (Loki, Grafana)
- **Honeycomb**: Strong via OTel Collector path

### Enterprise / Compliance
- **Splunk**: Established SIEM, compliance reporting
- **CrowdStrike Falcon LogScale**: Next-Gen SIEM, integrated with Falcon XDR ecosystem
- **Elastic**: Self-hosted for data sovereignty
- **Datadog**: SOC 2, HIPAA, FedRAMP options

## Architecture Pattern Comparison

### Pattern A: Lambda Direct Delivery
```
S3 AP → EventBridge → Lambda → Vendor API
```
- ✅ Simple, low cost (for low-volume logs)
- ❌ Throttling risk with high-volume logs
- ❌ Vendor-specific code per backend

### Pattern B: Via Firehose
```
S3 AP → Lambda (Transform) → Firehose → Vendor API
```
- ✅ Automatic buffering, high throughput
- ✅ Built-in retry and backpressure
- ❌ Firehose-compatible vendors only (Datadog, Splunk, New Relic, Dynatrace)
- ❌ Additional Firehose cost

### Pattern C: Via OTel Collector
```
S3 AP → Lambda (OTLP) → OTel Collector → Multiple Backends
```
- ✅ Vendor-neutral Lambda code (unchanged across backends)
- ✅ Multi-backend fan-out from single pipeline
- ✅ Routing, filtering, redaction in Collector config
- ❌ Requires Collector infrastructure (ECS Fargate recommended)
- ❌ Additional operational complexity
