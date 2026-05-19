# Migration Guide: Vendor Direct Send → OTel Collector Path

## Overview

Step-by-step instructions for migrating from direct vendor delivery (Datadog/New Relic/Splunk etc.) to the OTel Collector path. Zero-downtime migration is achievable.

## Prerequisites

- Existing vendor-direct Lambda is operational
- OTel Collector configuration file is prepared
- Credentials for both old and new backends are available

## Migration Steps

### Step 1: Deploy OTel Collector

Deploy the OTel Collector without affecting the existing environment.

```bash
# Docker (local/development)
docker run -d --name otel-collector \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env \
  otel/opentelemetry-collector-contrib:0.152.0

# Verify health check
curl -f http://localhost:13133/
```

For ECS Fargate:

```bash
aws cloudformation deploy \
  --template-file template-collector.yaml \
  --stack-name fsxn-otel-collector \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

### Step 2: Configure OTel Collector (Old Backend + New Backend)

During migration, deliver logs to both the existing and new backends.

```yaml
# otel-collector-config-migration.yaml
exporters:
  # Existing backend (e.g., Datadog)
  datadog:
    api:
      key: ${env:DD_API_KEY}
      site: ${env:DD_SITE}

  # New backend (e.g., Grafana Cloud)
  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [datadog, otlp_http/grafana]  # Deliver to both
```

### Step 3: Deploy New Lambda

The OTel Collector Lambda (`handler.py`) sends in OTLP format, which is different from the existing vendor-specific Lambda. Deploy the new Lambda alongside the old one.

```bash
# Deploy new OTel Lambda
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=<your-s3-ap-arn> \
    OtlpEndpoint=http://<collector-endpoint>:4318 \
    S3BucketName=<your-bucket> \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

### Step 4: Parallel Operation and Verification

Run both old and new Lambdas in parallel to verify data consistency.

```bash
# Send test event to new Lambda
aws lambda invoke \
  --function-name fsxn-otel-integration-shipper \
  --payload file://tests/test_data/sample_s3_event.json \
  --cli-binary-format raw-in-base64-out \
  /tmp/otel-response.json

# Check response
cat /tmp/otel-response.json
# Expected: {"statusCode": 200, "body": {"total_logs": N, "total_shipped": N, "errors": []}}
```

Verification checklist:
- [ ] Logs arriving at new backend
- [ ] Structured attributes correctly mapped
- [ ] Logs still arriving at existing backend
- [ ] Latency within acceptable range

### Recommended Parallel Run Duration

For enterprise and mission-critical workloads:

- **Minimum**: One full audit rotation cycle (typically 1-7 days depending on ONTAP audit rotation schedule)
- **Recommended**: 2-4 weeks for production workloads
- **Mission-critical**: 4+ weeks with formal operational sign-off

During parallel run, validate:
- Event count parity between old and new paths (tolerance: ±1%)
- All critical attributes present and searchable in new backend
- Alerting and runbooks function correctly with Collector-delivered data
- No unexpected latency or data loss patterns

### Step 5: Switch EventBridge Rule Target

After verification, switch the EventBridge rule target to the new Lambda.

```bash
# Check existing rule targets
aws events list-targets-by-rule \
  --rule fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1

# Add new Lambda as target (or update existing rule)
aws events put-targets \
  --rule fsxn-otel-s3-trigger \
  --targets "Id=OtelShipper,Arn=<new-lambda-arn>"
```

### Step 6: Disable Old Lambda

After confirming the new path is stable, disable the old Lambda.

```bash
# Disable old EventBridge rule (disable, don't delete)
aws events disable-rule \
  --name fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1
```

> **Note**: Keep the rule disabled for 1-2 weeks before deleting. This allows immediate rollback if issues arise.

### Step 7: Remove Old Backend Exporter from OTel Collector

After migration is complete, remove the old backend from the Collector config.

```yaml
# Remove old backend
exporters:
  # datadog:  ← removed
  #   api:
  #     key: ${env:DD_API_KEY}
  #     site: ${env:DD_SITE}

  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_http/grafana]  # New backend only
```

```bash
# Restart Collector to apply config
docker restart otel-collector
```

## Rollback Procedure

Steps to roll back if issues occur.

### Immediate Rollback (at Step 5-6 stage)

```bash
# 1. Re-enable old EventBridge rule
aws events enable-rule \
  --name fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1

# 2. Disable new EventBridge rule
aws events disable-rule \
  --name fsxn-otel-s3-trigger \
  --region ap-northeast-1
```

### Full Rollback

```bash
# 1. Verify old Lambda stack exists
aws cloudformation describe-stacks \
  --stack-name fsxn-<old-vendor>-integration \
  --region ap-northeast-1

# 2. Re-enable old rule
aws events enable-rule \
  --name fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1

# 3. Delete new stack (optional)
aws cloudformation delete-stack \
  --stack-name fsxn-otel-integration \
  --region ap-northeast-1
```

## Recommended Migration Timeline

| Day | Action | Risk |
|-----|--------|------|
| Day 1 | Step 1-2: Deploy Collector | None (no impact on existing) |
| Day 2-3 | Step 3-4: Deploy new Lambda + parallel run | Low (test events only) |
| Day 4-5 | Step 5: Switch EventBridge | Medium (production traffic) |
| Day 5-14 | Monitoring period | Low (rollback available) |
| Day 15 | Step 6: Disable old Lambda | Low |
| Day 30 | Step 7: Remove old exporter + delete old stack | None |

## Important Notes

- Log duplication may occur during migration (both old and new process the same events)
- If deduplication is needed at the backend, filter by `trace_id` or `event_id`
- The Lambda code is entirely different — treat this as a "new deployment" not a "code change"
- Keep the old Lambda code as reference until the OTel Lambda is stable
