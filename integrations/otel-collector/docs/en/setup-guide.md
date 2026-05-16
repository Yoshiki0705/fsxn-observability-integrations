# OpenTelemetry Collector Setup Guide

🌐 [日本語](../ja/setup-guide.md)

## Overview

Vendor-neutral OTLP/HTTP integration for shipping FSx ONTAP audit logs to any compatible backend.

## Prerequisites

- OTLP-compatible backend (Grafana, Honeycomb, Datadog, Jaeger, etc.)
- [Prerequisites stack](../../../docs/en/prerequisites.md) deployed

## Step 1: Prepare OTLP Endpoint

### Grafana Cloud
```
Endpoint: https://otlp-gateway-prod-ap-southeast-0.grafana.net/otlp
Headers: Authorization=Basic <base64(instance_id:api_key)>
```

### Honeycomb
```
Endpoint: https://api.honeycomb.io
Headers: x-honeycomb-team=<api-key>,x-honeycomb-dataset=fsxn-audit
```

### Self-hosted Collector
```
Endpoint: http://<collector-host>:4318
```

## Step 2: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    OtlpEndpoint=https://otlp-gateway.grafana.net/otlp \
    OtlpHeaders="Authorization=Basic xxx" \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Verify

Upload test event and confirm log arrival in your backend.

## Self-hosted Collector Config

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
processors:
  batch:
    timeout: 5s
exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [loki]
```

## Benefits

- No vendor lock-in: Switch backends without code changes
- Multi-destination: Fan-out to multiple backends simultaneously
- Standard format: CNCF OpenTelemetry Log Data Model
