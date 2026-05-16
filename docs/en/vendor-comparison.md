# Vendor Comparison

## Supported Vendors

| Vendor | Delivery Method | Auth Method | Max Batch Size | Firehose Support |
|--------|----------------|-------------|----------------|-----------------|
| Datadog | Logs API v2 | API Key (Header) | 5MB/request | ✅ |
| New Relic | Log API | License Key (Header) | 1MB/request | ✅ |
| Grafana Cloud | Loki Push API | Basic Auth | No limit (4MB recommended) | ❌ |
| Splunk | HEC | HEC Token (Header) | No limit | ✅ (Built-in) |
| Elastic | Bulk API | API Key / Basic Auth | No limit (10MB recommended) | ❌ |
| Dynatrace | Log Ingest API | API Token (Header) | 1MB/request | ✅ |
| Sumo Logic | HTTP Source | Embedded in URL | 1MB/request | ❌ |
| Honeycomb | Events API | API Key (Header) | 5MB/request | ❌ |
| OTel Collector | OTLP/HTTP | Configurable | Configurable | ❌ |

## Selection Guide

### Cost-Focused
- **Sumo Logic**: Free tier available (500MB/day)
- **Grafana Cloud**: Free tier available (50GB/month)
- **Elastic**: Self-hosted option

### Existing Environment Integration
- **Datadog**: Already using Datadog
- **Splunk**: Existing Splunk environment (serverless migration)
- **Dynatrace**: Want APM integration

### Vendor Lock-in Avoidance
- **OTel Collector**: Vendor-neutral, easy future switching
- **Grafana Cloud**: OSS-based stack

## Architecture Pattern Comparison

### Pattern A: Lambda Direct Delivery
```
S3 AP → EventBridge → Lambda → Vendor API
```
- ✅ Simple, low cost (for low-volume logs)
- ❌ Throttling risk with high-volume logs

### Pattern B: Via Firehose
```
S3 AP → Lambda (Transform) → Firehose → Vendor API
```
- ✅ Automatic buffering, high throughput
- ❌ Firehose-compatible vendors only, additional cost
