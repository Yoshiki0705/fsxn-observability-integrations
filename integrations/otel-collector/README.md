# FSx for ONTAP OpenTelemetry Collector Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

## Overview

Vendor-neutral integration using OpenTelemetry Protocol (OTLP/HTTP). Ships FSx ONTAP audit logs to **any** OTLP-compatible backend without vendor lock-in.

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → OTLP/HTTP → Any Backend
                                                          │
                                                          ├── Grafana Cloud (Loki)
                                                          ├── Honeycomb
                                                          ├── Datadog
                                                          ├── Jaeger
                                                          ├── AWS X-Ray (via ADOT)
                                                          └── Self-hosted OTel Collector
```

## Why OTLP?

- **Vendor-neutral**: Switch backends without changing Lambda code
- **Standard format**: OpenTelemetry Log Data Model
- **Flexible routing**: OTel Collector can fan-out to multiple backends simultaneously
- **Future-proof**: Industry-standard backed by CNCF

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    OtlpEndpoint=https://otlp-gateway.example.com:4318 \
    OtlpHeaders="Authorization=Bearer token123" \
    S3BucketName=my-fsxn-audit-bucket \
    OtelServiceName=fsxn-ontap-audit \
  --capabilities CAPABILITY_IAM
```

## Supported Backends

| Backend | OTLP Endpoint | Auth |
|---------|---------------|------|
| Grafana Cloud | `https://otlp-gateway-<region>.grafana.net/otlp` | Basic Auth (Instance ID + API Key) |
| Honeycomb | `https://api.honeycomb.io` | `x-honeycomb-team=<key>` |
| Datadog | `https://http-intake.logs.datadoghq.com` | `DD-API-KEY=<key>` |
| New Relic | `https://otlp.nr-data.net` | `api-key=<key>` |
| AWS ADOT | `http://adot-collector:4318` | IAM (within VPC) |
| Self-hosted | `http://otel-collector:4318` | Configurable |

## OTLP Log Record Format

```json
{
  "resourceLogs": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "fsxn-ontap-audit"}},
        {"key": "cloud.provider", "value": {"stringValue": "aws"}},
        {"key": "cloud.platform", "value": {"stringValue": "aws_fsx"}}
      ]
    },
    "scopeLogs": [{
      "scope": {"name": "fsxn-observability", "version": "0.1.0"},
      "logRecords": [{
        "timeUnixNano": "1705315200000000000",
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": "..."},
        "attributes": [
          {"key": "event.type", "value": {"stringValue": "4663"}},
          {"key": "user.name", "value": {"stringValue": "admin@corp.local"}},
          {"key": "fsxn.operation", "value": {"stringValue": "ReadData"}},
          {"key": "fsxn.path", "value": {"stringValue": "/vol/data/file.txt"}}
        ]
      }]
    }]
  }]
}
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `OtlpEndpoint` | ✅ | - | OTLP/HTTP endpoint (e.g., `http://collector:4318`) |
| `OtlpHeaders` | ❌ | - | Extra headers as `key=value,key2=value2` |
| `ApiKeySecretArn` | ❌ | - | Secrets Manager ARN for Bearer token |
| `OtelServiceName` | ❌ | `fsxn-ontap-audit` | `service.name` resource attribute |
| `OtelResourceAttributes` | ❌ | - | Extra resource attrs as `key=value,...` |

## Self-Hosted Collector Configuration

Example `otel-collector-config.yaml` for receiving and routing logs:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1000

exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
  otlphttp/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${HONEYCOMB_API_KEY}

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [loki, otlphttp/honeycomb]
```
