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
| Sumo Logic | 1.25 credits/day (~20 credits/month) | $0 | $0 | ~$300 | Credit-based (Flex) |
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
- **New Relic**: Largest free tier (100 GB/month, permanent)
- **Grafana Cloud**: Good free tier (50 GB/month) + OSS ecosystem
- **Sumo Logic**: Free tier available (1.25 credits/day (Flex model))
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

## Trial & Verification Notes

### Splunk Cloud Platform

The Splunk Cloud Platform **free trial does NOT provision HEC DNS records** (`http-inputs-<stack>.splunkcloud.com`). This is a [widely reported issue](https://community.splunk.com/t5/Getting-Data-In/HEC-with-Splunk-Cloud-trial/td-p/596680) in the Splunk Community (2020–2025). Port 8088 is also blocked on the trial instance.

**Workaround**: Use Splunk Enterprise (Docker) for local E2E validation at $0 cost. The `splunk/splunk:latest` image includes a fully functional HEC. Our E2E verification was completed with Splunk Enterprise 10.4.0 (Docker, linux/amd64).

### CrowdStrike Falcon LogScale

The CrowdStrike Falcon **EDR trial** includes read-only access to the Next-Gen SIEM UI (log search, repository list) but **does NOT include the Data Connectors / HEC ingest functionality**. The "Add data connector" page returns "Page not found" on the trial. A paid Falcon Next-Gen SIEM license is required for external data ingestion via HEC.

**Protocol verification**: Since Falcon LogScale uses a Splunk HEC-compatible endpoint (`/api/v1/ingest/hec`), the Splunk Enterprise E2E test validates the identical HEC payload format used by this integration.

### Verification Summary

| Vendor | E2E Method | Cost |
|--------|-----------|------|
| Datadog | Cloud trial (14-day) | $0 |
| New Relic | Free tier (100 GB/month) | $0 |
| Grafana Cloud | Free tier (50 GB/month) | $0 |
| Splunk | Docker local (Enterprise trial) | $0 |
| Elastic | Cloud trial (14-day) | $0 |
| Dynatrace | Free tier (15-day trial) | $0 |
| Sumo Logic | Free tier (1.25 credits/day (Flex model)) | $0 |
| Honeycomb | Free tier (20M events/month) | $0 |
| CrowdStrike | HEC protocol verified via Splunk | $0 |
| OTel Collector | Self-hosted (Docker Compose) | $0 |
