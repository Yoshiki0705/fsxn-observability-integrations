# OTel Collector Integration

FSx for ONTAP audit log shipping via OTLP/HTTP to an OpenTelemetry Collector, enabling vendor-neutral multi-backend delivery (Grafana Cloud + Honeycomb).

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

## Documentation

- [Japanese Setup Guide](docs/ja/setup-guide.md)
- [English Setup Guide](docs/en/setup-guide.md)

## Verification

```bash
# Run E2E verification script
bash ../../scripts/verify-otel-e2e.sh --stack-name fsxn-otel-integration --region ap-northeast-1
```
