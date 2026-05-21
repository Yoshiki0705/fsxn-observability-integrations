# Shared Python Utilities

Common modules for all FSx ONTAP observability Lambda handlers.

## Modules

### observability.py

Standardized structured logging, custom metrics, and distributed tracing using [AWS Lambda Powertools for Python](https://docs.powertools.aws.dev/lambda/python/latest/).

```python
from shared.python.observability import logger, metrics, tracer, MetricUnit

@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event, context):
    logger.info("Processing started")
    metrics.add_metric(name="RecordsParsed", unit=MetricUnit.Count, value=10)
```

**Standard Metrics:**

| Metric | Unit | Description |
|--------|------|-------------|
| RecordsParsed | Count | Audit log records parsed from S3 object |
| RecordsShipped | Count | Records successfully delivered to backend |
| DeliveryFailures | Count | Failed delivery attempts (after retries) |
| CheckpointAgeSeconds | Seconds | Time since last successful checkpoint update |
| BatchSizeBytes | Bytes | Size of payload sent to backend |
| DeliveryLatencyMs | Milliseconds | Time from parse to backend acknowledgment |
| PoisonPillFiles | Count | Files that consistently fail processing |

**Required Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| POWERTOOLS_SERVICE_NAME | fsxn-observability | Service name in logs and traces |
| POWERTOOLS_METRICS_NAMESPACE | FSxNObservability | CloudWatch Metrics namespace |
| POWERTOOLS_LOG_LEVEL | INFO | Minimum log level |

### idempotency.py

DynamoDB-backed object ledger for exactly-once processing (Production Readiness Level 3).

```python
from shared.python.idempotency import ObjectLedger

ledger = ObjectLedger(table_name="fsxn-object-ledger")

if ledger.is_processed(object_key):
    return  # Skip duplicate

# ... process ...

ledger.mark_processed(object_key, record_count=42)
```

**DynamoDB Table Schema:**

| Attribute | Type | Description |
|-----------|------|-------------|
| object_key | String (PK) | S3 object key |
| processed_at | Number | Unix timestamp of processing |
| record_count | Number | Records extracted |
| ttl | Number | DynamoDB TTL epoch |

## Installation

For Lambda deployment, include these modules in a Lambda Layer or bundle them with the function code:

```bash
# As a Lambda Layer
cd shared/python
zip -r ../../shared-python-layer.zip .
aws lambda publish-layer-version \
  --layer-name fsxn-shared-python \
  --zip-file fileb://../../shared-python-layer.zip \
  --compatible-runtimes python3.12
```

## Dependencies

```
aws-lambda-powertools[tracer]>=2.0.0
boto3>=1.28.0
```
