# OTel Collector Integration

FSx for ONTAP audit log shipping via OTLP/HTTP to an OpenTelemetry Collector, enabling vendor-neutral multi-backend delivery.

> **✅ All Backends Verified Working** (2026-05-18)
>
> | Backend | Status | Config File |
> |---------|--------|-------------|
> | Datadog (ap1.datadoghq.com) | ✅ Verified | `otel-collector-config-datadog.yaml` |
> | Grafana Cloud (ap-northeast-0) | ✅ Verified | `otel-collector-config.yaml` |
> | Honeycomb | ✅ Verified | `otel-collector-config.yaml` |
> | Multi-Backend (Grafana + Honeycomb) | ✅ Verified | `otel-collector-config.yaml` |
> | Triple (Datadog + Grafana + Honeycomb) | ✅ Verified | `otel-collector-config-triple.yaml` |
>
> Tested with `otel/opentelemetry-collector-contrib:0.152.0`. Lambda code unchanged across all backends.

## Architecture

```
S3 Access Point → Lambda (OTLP Shipper) → OTel Collector → Grafana Cloud (OTLP)
                                                         → Honeycomb (OTLP)
                                                         → Datadog (exporter)
EMS Webhook    → Lambda (EMS Handler)   → OTel Collector → (same backends)
FPolicy Events → Lambda (FPolicy)       → OTel Collector → (same backends)
```

## 5-Minute Local Validation

Validate the entire pipeline locally in under 5 minutes with a single backend:

```bash
# 1. Configure credentials (one backend only)
cp .env.example .env
# Edit .env with ONE backend credential (e.g., Honeycomb API key)

# 2. Start OTel Collector
docker run -d --name otel-collector \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env \
  otel/opentelemetry-collector-contrib:0.152.0

# 3. Generate a fresh OTLP payload (avoids stale timestamp rejection)
bash scripts/generate-otlp-payload.sh --output /tmp/p.json

# 4. Send payload to Collector
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d @/tmp/p.json

# 5. Check your backend for service_name=fsxn-audit
#    Grafana: {job="fsxn-audit"} | Honeycomb: dataset=fsxn-audit | Datadog: service:fsxn-audit
```

If step 4 returns HTTP 200, the Collector accepted the payload. Check your backend within 1-2 minutes.

## Quick Start

```bash
# 1. Configure credentials
cp .env.example .env  # Edit with your Grafana + Honeycomb credentials

# 2. Start OTel Collector locally
# Option A: docker compose (if available)
docker compose up -d

# Option B: docker run (fallback for Colima)
docker run -d --name otel-collector \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env \
  otel/opentelemetry-collector-contrib:0.152.0

# 3. Verify health
curl -f http://localhost:13133/

# 4. Run tests
python -m pytest tests/ -v
```

## Multi-Backend (Grafana Cloud + Honeycomb)

The default configuration delivers logs simultaneously to both Grafana Cloud and Honeycomb.

> The `health_check` extension confirms the Collector process is available; it does not guarantee that each backend exporter is successfully delivering logs. Monitor exporter errors separately using the Collector's internal telemetry metrics if enabled.

### Verified Auth Patterns

**Grafana Cloud (OTLP Gateway)**:
- Endpoint: `https://otlp-gateway-prod-<region>.grafana.net/otlp`
- Auth: `Authorization: Basic <base64(instanceId:apiToken)>`
- Instance ID is numeric (e.g., 1649835)
- Exporter: `otlp_http/grafana` (NOT the `loki` exporter)

**Honeycomb**:
- Endpoint: `https://api.honeycomb.io`
- Auth: `x-honeycomb-team: <ingest-api-key>` header
- Dataset: `x-honeycomb-dataset: fsxn-audit` header
- Ingest keys start with `hcaik_`

### Test Multi-Backend Locally

```bash
bash scripts/test-local-multi-backend.sh
```

## Components

| Component | File | Description |
|-----------|------|-------------|
| Lambda OTLP Shipper | `lambda/handler.py` | Reads S3 audit logs, maps to OTLP, sends via HTTP |
| EMS Handler | `lambda/ems_handler.py` | Receives EMS webhook events, forwards as OTLP |
| FPolicy Handler | `lambda/fpolicy_handler.py` | Receives FPolicy events from EventBridge, forwards as OTLP |
| OTel Config (default) | `otel-collector-config.yaml` | Grafana Cloud + Honeycomb (otlp_http) |
| OTel Config (Datadog) | `otel-collector-config-datadog.yaml` | Datadog exporter |
| OTel Config (Triple) | `otel-collector-config-triple.yaml` | Datadog + Grafana + Honeycomb simultaneous |
| Docker Compose | `docker-compose.yaml` | Local OTel Collector (pinned 0.152.0) |
| CloudFormation | `template.yaml` | AWS deployment template |

## Testing

```bash
# Unit + property tests
python -m pytest tests/ -v

# Property tests only
python -m pytest tests/test_handler_properties.py -v

# Bilingual comparison
python -m pytest tests/test_bilingual_properties.py -v

# Generate fresh OTLP payload (avoids stale timestamp rejection)
bash scripts/generate-otlp-payload.sh --output /tmp/payload.json
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

# 4. Run automated test
bash scripts/test-local-datadog.sh
```

This proves the key architectural point: **Lambda code is UNCHANGED** — only the Collector config changes to route logs to Datadog.

## Troubleshooting

### Timestamp Rejection

Datadog rejects logs older than ~18 hours. Grafana Cloud and Honeycomb also prefer recent timestamps. Use the payload generator to create fresh test data:

```bash
bash scripts/generate-otlp-payload.sh --output /tmp/fresh-payload.json
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d @/tmp/fresh-payload.json
```

### Colima / Docker Compose Compatibility

`docker compose` v2 plugin is NOT available in Colima. All scripts detect this and fall back to `docker run`. If you see "docker compose: command not found", this is expected.

### Grafana Cloud Auth Format

The `loki` exporter is NOT the correct approach for OTLP → Grafana Cloud. Use `otlp_http/grafana` with the OTLP gateway endpoint:
- ❌ `loki` exporter with Loki push API
- ✅ `otlp_http/grafana` with `https://otlp-gateway-prod-<region>.grafana.net/otlp`

Basic Auth value must be `base64(instanceId:apiToken)` — NOT `instanceId:apiToken` in plain text.

### Honeycomb Auth

Ingest API keys start with `hcaik_`. Environment keys (`hcxik_`) will NOT work for data ingestion.

## Documentation

- [Japanese Setup Guide](docs/ja/setup-guide.md)
- [English Setup Guide](docs/en/setup-guide.md)
- [Verification Results (JA)](../../docs/ja/verification-results-otel-collector.md)
- [Verification Results (EN)](../../docs/en/verification-results-otel-collector.md)

## Verification

```bash
# Run E2E verification script
bash ../../scripts/verify-otel-e2e.sh --stack-name fsxn-otel-integration --region ap-northeast-1
```
