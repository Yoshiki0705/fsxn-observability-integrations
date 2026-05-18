# OTel Collector Integration

FSx for ONTAP audit log shipping via OTLP/HTTP to an OpenTelemetry Collector, enabling vendor-neutral multi-backend delivery (Grafana Cloud + Honeycomb).

> **✅ Verified Working**: FPolicy → OTel Collector → Datadog path confirmed operational (2026-05-18).
> Tested with `otel/opentelemetry-collector-contrib:0.152.0`. Lambda code unchanged across backends.

## Architecture

```
S3 Access Point → Lambda (OTLP Shipper) → OTel Collector → Grafana Cloud (Loki)
                                                         → Honeycomb
```

## Quick Start

```bash
# 1. Start OTel Collector locally
cp .env.example .env  # Edit with your credentials
docker compose up -d

# 2. Verify health
curl -f http://localhost:13133/

# 3. Run tests
python -m pytest tests/ -v
```

## Components

| Component | File | Description |
|-----------|------|-------------|
| Lambda OTLP Shipper | `lambda/handler.py` | Reads S3 audit logs, maps to OTLP, sends via HTTP |
| EMS Handler | `lambda/ems_handler.py` | Receives EMS webhook events, forwards as OTLP |
| FPolicy Handler | `lambda/fpolicy_handler.py` | Receives FPolicy events from EventBridge, forwards as OTLP |
| OTel Collector Config | `otel-collector-config.yaml` | Receiver → Batch → Loki + Honeycomb |
| Docker Compose | `docker-compose.yaml` | Local OTel Collector environment |
| CloudFormation | `template.yaml` | AWS deployment template |

## Testing

```bash
# Unit + property tests
python -m pytest tests/ -v

# Property tests only
python -m pytest tests/test_handler_properties.py -v

# Bilingual comparison
python -m pytest tests/test_bilingual_properties.py -v
```

## Deployment

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=<ARN> \
    OtlpEndpoint=<endpoint> \
    ApiKeySecretArn=<ARN> \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

## Alternative: Datadog Backend

The default configuration targets Grafana Cloud + Honeycomb. To use **Datadog** as the backend instead:

```bash
# 1. Configure Datadog credentials
cp .env.datadog.example .env.datadog
# Edit .env.datadog with your DD_API_KEY and DD_SITE
# DD_SITE examples: datadoghq.com (US1), ap1.datadoghq.com (AP1/Japan)

# 2. Start OTel Collector with Datadog config
# Option A: docker compose (if available)
docker compose -f docker-compose-datadog.yaml --env-file .env.datadog up -d

# Option B: docker run (fallback for Colima or environments without compose plugin)
docker run -d --name otel-collector-datadog \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config-datadog.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env.datadog \
  otel/opentelemetry-collector-contrib:0.152.0

# 3. Verify health
curl -f http://localhost:13133/

# 4. Send test OTLP payload
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d @tests/test_data/sample_otlp_payload.json
```

This proves the key architectural point: **Lambda code is UNCHANGED** — only the Collector config changes to route logs to Datadog.

| File | Purpose |
|------|---------|
| `otel-collector-config-datadog.yaml` | Collector config with Datadog exporter |
| `docker-compose-datadog.yaml` | Docker Compose using Datadog config |
| `.env.datadog.example` | Template for Datadog credentials |

## Documentation

- [Japanese Setup Guide](docs/ja/setup-guide.md)
- [English Setup Guide](docs/en/setup-guide.md)

## Verification

```bash
# Run E2E verification script
bash ../../scripts/verify-otel-e2e.sh --stack-name fsxn-otel-integration --region ap-northeast-1
```
