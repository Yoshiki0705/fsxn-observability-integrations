# OTel Collector Integration Setup Guide

This guide walks you through setting up the FSx for ONTAP audit log pipeline that delivers logs simultaneously to Grafana Cloud (Loki) and Honeycomb via an OpenTelemetry Collector.

## Prerequisites

- Docker and Docker Compose installed
- AWS CLI v2 configured (`aws configure`)
- FSx for ONTAP S3 Access Point created
- Grafana Cloud account (Loki endpoint, User ID, API Token)
- Honeycomb account (API Key)
- Python 3.12 (for Lambda development)

## OTel Collector Docker Setup

Run the OTel Collector locally to receive logs via OTLP/HTTP.

### Docker Compose Configuration

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.152.0
    ports:
      - "4318:4318"   # OTLP HTTP
      - "13133:13133" # Health check
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml
    environment:
      - GRAFANA_OTLP_ENDPOINT=${GRAFANA_OTLP_ENDPOINT}
      - GRAFANA_BASIC_AUTH=${GRAFANA_BASIC_AUTH}
      - HONEYCOMB_API_KEY=${HONEYCOMB_API_KEY}
      - HONEYCOMB_DATASET=${HONEYCOMB_DATASET:-fsxn-audit}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:13133/"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    restart: unless-stopped
```

> **Note**: On macOS with Colima, the `docker compose` v2 plugin is not available. Use `docker run` as a fallback:
> ```bash
> docker run -d --name otel-collector \
>   -p 4318:4318 -p 13133:13133 \
>   -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
>   --env-file .env \
>   otel/opentelemetry-collector-contrib:0.152.0
> ```

### Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### Start the Collector

```bash
cd integrations/otel-collector
docker compose up -d
```

Verify the health check:

```bash
curl -f http://localhost:13133/
```

## Collector YAML Configuration

The OTel Collector config defines an OTLP receiver, batch processor, and dual exporters for Grafana Cloud and Honeycomb.

> **Important**: Use the `otlp_http/grafana` exporter (NOT the `loki` exporter) for OTLP → Grafana Cloud. The OTLP gateway endpoint handles log ingestion natively.

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
  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

  otlp_http/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${env:HONEYCOMB_API_KEY}
      x-honeycomb-dataset: ${env:HONEYCOMB_DATASET}

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_http/grafana, otlp_http/honeycomb]
```

This configuration automatically fans out OTLP logs from the Lambda to both Grafana Cloud and Honeycomb simultaneously.

### Verified Auth Patterns

**Grafana Cloud**:
- Endpoint: `https://otlp-gateway-prod-<region>.grafana.net/otlp`
- Auth: `Basic base64(instanceId:apiToken)`
- Instance ID is numeric (e.g., 1649835)
- Region example: `ap-northeast-0` (Japan)

**Honeycomb**:
- Endpoint: `https://api.honeycomb.io`
- Auth: `x-honeycomb-team` header with Ingest API Key
- Ingest keys start with `hcaik_`

## CloudFormation Deployment

Deploy the Lambda function and supporting resources to AWS.

### Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `S3AccessPointArn` | FSx ONTAP S3 AP ARN | `arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit` |
| `OtlpEndpoint` | OTel Collector endpoint | `http://collector:4318` |
| `ApiKeySecretArn` | Auth token Secret ARN (optional) | `arn:aws:secretsmanager:...` |
| `ServiceName` | OTLP service.name attribute | `fsxn-audit` |
| `S3BucketName` | Audit log bucket name | `fsxn-audit-logs-bucket` |

### Deploy Command

```bash
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    OtlpEndpoint=http://your-collector:4318 \
    S3BucketName=fsxn-audit-logs-bucket \
    ServiceName=fsxn-audit \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

## Test Event Invocation

Send a test event to the Lambda function to verify the pipeline.

```bash
aws lambda invoke \
  --function-name fsxn-otel-integration-shipper \
  --payload file://integrations/otel-collector/tests/test_data/sample_s3_event.json \
  --cli-binary-format raw-in-base64-out \
  /tmp/otel-response.json

cat /tmp/otel-response.json
```

Expected response:

```json
{"statusCode": 200, "body": {"total_logs": 6, "total_shipped": 6, "errors": []}}
```

## Verification Steps

### 1. Check Lambda Execution Logs

Confirm successful OTLP delivery in CloudWatch Logs:

```bash
aws logs tail /aws/lambda/fsxn-otel-integration-shipper --since 5m
```

Expected output: Log entries showing `OTLP payload sent successfully`.

![CloudWatch OTLP delivery success](../../../../docs/screenshots/01-cloudwatch-otlp-success.png)

### 2. Verify Log Arrival in Grafana Cloud

In Grafana Cloud Explore, run the following query:

- Data source: Loki
- Query: `{job="fsxn-audit"}`

Confirm that FSx ONTAP audit logs appear within 5 minutes. Verify that `event.type`, `user.name`, and `fsxn.operation` attributes are present.

![Grafana Cloud log arrival](../../../../docs/screenshots/02-grafana-logs-arrival.png)

### 3. Verify Log Arrival in Honeycomb

Query the `fsxn-audit` dataset in Honeycomb:

- Dataset: `fsxn-audit`
- Time range: Last 5 minutes

Confirm that FSx ONTAP audit logs appear within 5 minutes.

### 4. Multi-Backend Consistency Check

Verify that the same event (matching timestamp and file path) appears in both Grafana Cloud and Honeycomb.

## Honeycomb-Only Configuration

To use **Honeycomb as the sole backend** without Grafana Cloud, swap the OTel Collector config. No Lambda code changes are required.

### Honeycomb-Only Collector Configuration

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
  otlp_http/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${env:HONEYCOMB_API_KEY}
      x-honeycomb-dataset: ${env:HONEYCOMB_DATASET}

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_http/honeycomb]
```

### Environment Variables

```bash
# .env.honeycomb
HONEYCOMB_API_KEY=hcaik_your_ingest_key_here
HONEYCOMB_DATASET=fsxn-audit
```

### Start Command

```bash
# Honeycomb 専用設定ファイルを作成後:
docker run -d --name otel-collector-honeycomb \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config-honeycomb.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env.honeycomb \
  otel/opentelemetry-collector-contrib:0.152.0
```

> **Note**: Honeycomb Ingest API Keys start with `hcaik_`. Environment keys (`hcxik_`) will NOT work for data ingestion.

## Datadog Backend Configuration

To use **Datadog** as the backend instead of Grafana Cloud + Honeycomb, swap the OTel Collector config file. No Lambda code changes are required — only the Collector configuration determines the destination.

### Datadog Collector Configuration

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
  datadog:
    api:
      key: ${env:DD_API_KEY}
      site: ${env:DD_SITE}

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [datadog]
```

### Starting Docker Compose (Datadog Variant)

```bash
# 1. Configure credentials
cp .env.datadog.example .env.datadog
# Edit .env.datadog with your DD_API_KEY and DD_SITE
# DD_SITE examples:
#   datadoghq.com (US1), datadoghq.eu (EU),
#   ap1.datadoghq.com (AP1/Japan), us3.datadoghq.com (US3)

# 2. Start OTel Collector with Datadog config
# Option A: docker compose (if available)
docker compose -f docker-compose-datadog.yaml --env-file .env.datadog up -d

# Option B: docker run (fallback for Colima or environments without compose plugin)
docker run -d --name otel-collector-datadog \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config-datadog.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env.datadog \
  otel/opentelemetry-collector-contrib:0.152.0

# 3. Verify health check
curl -f http://localhost:13133/
```

> **Note**: On macOS with Colima, the `docker compose` v2 plugin may not be available. Use Option B (`docker run`) as a fallback.

### Verification in Datadog

1. Log in to the Datadog Logs UI
2. Enter `source:fsxn-audit` or `service:fsxn-ontap` (for FPolicy) in the search filter
3. Confirm FSx ONTAP logs arrive within 5 minutes
4. Verify structured attributes are present:
   - **S3 Audit Logs**: `event.type`, `user.name`, `fsxn.operation`, `client.address`, `fsxn.result`, `fsxn.path`
   - **FPolicy**: `client_ip`, `file_path`, `operation_type`, `volume_name`, `event_id`, `timestamp`, `file_size`, `svm`/`vserver`

> **Verified**: FPolicy → OTel Collector → Datadog path confirmed operational (2026-05-18).
> Logs appear as Service: `fsxn-ontap`, Source: `fsxn-fpolicy` in Datadog.

### Local Test Script

Run the automated local test:

```bash
bash scripts/test-local-datadog.sh
```

This script automatically:
- Starts the OTel Collector with Datadog config
- Verifies the health check
- Sends a sample OTLP payload
- Checks collector logs for export activity
- Cleans up


## Triple Backend (Datadog + Grafana Cloud + Honeycomb)

To deliver logs simultaneously to **all three backends** (Datadog, Grafana Cloud, and Honeycomb) from a single OTLP stream, use the triple-backend config. No Lambda code changes are required.

### Start the Triple-Backend Collector

```bash
# Start with triple-backend config
docker run -d --name otel-collector-triple \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config-triple.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env.triple \
  otel/opentelemetry-collector-contrib:0.152.0
```

### Environment Variables

```bash
cp .env.triple.example .env.triple
# Edit .env.triple with your credentials for all 3 backends
```

### service.name Mapping

S3 audit logs use `service.name=fsxn-audit`, EMS uses `service.name=fsxn-ems`, and FPolicy uses `service.name=fsxn-fpolicy`.

> Depending on your Honeycomb environment and dataset model, `x-honeycomb-dataset` may be optional or handled differently. Refer to your Honeycomb OTLP setup page.

## Firehose Buffering Path (High Volume)

For high-volume scenarios exceeding 1,000 events/second, consider using Kinesis Data Firehose as an intermediate buffer instead of sending directly from Lambda to the OTel Collector.

### Architecture

```
S3 Access Point → Lambda → Kinesis Data Firehose → OTel Collector → Backends
                                    │
                                    ├── 自動バッファリング (60秒 or 1MB)
                                    ├── 自動リトライ
                                    └── バックプレッシャー処理
```

### When to Use the Firehose Path

| Condition | Direct Send | Firehose Path |
|-----------|-------------|---------------|
| Event volume | < 1,000/sec | > 1,000/sec |
| Latency requirement | Real-time (< 5s) | Near real-time (< 60s) |
| Burst tolerance | Depends on Lambda concurrency | Firehose auto-buffers |
| Cost | Lambda execution time only | + Firehose charges |
| Reliability | Lambda retry only | Firehose auto-retry + S3 backup |

### Firehose Configuration Example

```yaml
# CloudFormation snippet
FirehoseDeliveryStream:
  Type: AWS::KinesisFirehose::DeliveryStream
  Properties:
    DeliveryStreamName: fsxn-otel-firehose
    HttpEndpointDestinationConfiguration:
      EndpointConfiguration:
        Url: http://<collector-endpoint>:4318/v1/logs
        Name: OTelCollector
      BufferingHints:
        IntervalInSeconds: 60
        SizeInMBs: 1
      RetryOptions:
        DurationInSeconds: 300
      S3BackupMode: FailedDataOnly
      S3Configuration:
        BucketARN: arn:aws:s3:::fsxn-firehose-backup
        RoleARN: !GetAtt FirehoseRole.Arn
```

### Important Notes

- Firehose sends batched JSON to HTTP endpoints
- The OTel Collector may need to parse Firehose-formatted payloads
- Datadog and Splunk are available as native Firehose destinations (no OTel Collector needed)
- Firehose minimum buffer interval is 60 seconds — use direct send when real-time delivery is required
