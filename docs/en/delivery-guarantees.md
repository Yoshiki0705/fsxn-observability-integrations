# Delivery Guarantee Patterns

This document describes the delivery guarantee tiers available across all vendor integrations in this project. Choose the tier that matches your reliability requirements and operational complexity budget.

## Decision Matrix

| Tier | Delivery Guarantee | Complexity | Cost | When to Use |
|------|-------------------|-----------|------|-------------|
| Quickstart | At-least-once | Low | Lambda only | PoC, dev, low-volume production |
| Medium | At-least-once + replay | Medium | Lambda + SQS DLQ | Production with operational runbook |
| Higher reliability | At-least-once + buffering | High | Lambda + SQS + DynamoDB | High-volume, strict SLA |
| Multi-backend | At-least-once + routing | High | Collector compute | Multiple destinations, enrichment, redaction |

## Tier 1: Quickstart (This Project's Default)

```
EventBridge Scheduler → Lambda → Vendor API
                    ↓ (on failure)
              Scheduler DLQ
```

**Components**:
- Lambda direct send to vendor API
- EventBridge Scheduler retry policy (2 retries, 1-hour event age)
- Scheduler DLQ for failed invocations
- SSM Parameter Store high-watermark checkpoint
- Lambda reserved concurrency = 1 (overlap prevention)
- Processing bounds (MAX_KEYS_PER_RUN, SAFETY_THRESHOLD_MS)

**Delivery semantics**: At-least-once. If Lambda succeeds in sending but fails before updating the checkpoint, the next run re-processes those objects. Duplicates are possible but rare.

**Failure handling**:
- Transient vendor API errors → Lambda retries with exponential backoff (up to 3 attempts per invocation)
- Lambda timeout → Scheduler DLQ captures the failed invocation; next scheduled run retries from checkpoint
- Persistent failures → Scheduler DLQ accumulates; operator investigates

**Limitations**:
- No per-object retry tracking (poison-pill file blocks subsequent files)
- No buffering during vendor outages (relies on scheduler retry window)
- Single-concurrency limits throughput

## Tier 2: Medium Volume (Production with Replay)

```
EventBridge Scheduler → Lambda → Vendor API
                    ↓ (on failure)
              Scheduler DLQ
              Lambda failure destination → SQS
                                           ↓
                                    Replay runbook
```

**Additional components**:
- Lambda failure destination (async invocation → SQS on failure)
- Operational replay runbook (manual or automated DLQ drain)
- Pipeline health CloudWatch alarms
- Poison-pill detection (retry count tracking)

**When to upgrade from Quickstart**:
- You need visibility into individual object processing failures
- Vendor API has known maintenance windows > 1 hour
- Audit compliance requires proof of delivery or documented retry

**Implementation notes**:
- Add Lambda failure destination to capture failed async invocations
- Track per-object retry count in DynamoDB or SSM tags
- Implement poison-pill quarantine after N failures
- Set CloudWatch alarms on Scheduler DLQ depth, Lambda errors, checkpoint age

## Tier 3: Higher Reliability (SQS Buffering)

```
EventBridge Scheduler → Lambda (reader) → SQS buffer
                                              ↓
                                    Lambda (shipper) → Vendor API
                                              ↓ (on failure)
                                           SQS DLQ
```

**Additional components**:
- SQS queue between reader and shipper Lambdas
- Per-object checkpoint ledger (DynamoDB)
- DynamoDB conditional writes for deduplication
- SQS DLQ with automated replay
- Concurrent shipper Lambdas (SQS event source mapping)

**When to upgrade from Medium**:
- High event volume (>1000 files/hour)
- Vendor API has strict rate limits requiring backpressure
- Need concurrent processing with deduplication
- Require buffering during extended vendor outages

**Implementation notes**:
- Reader Lambda lists files and enqueues S3 keys to SQS
- Shipper Lambda processes one key per message (SQS event source mapping)
- DynamoDB tracks per-object state: PENDING → IN_PROGRESS → COMPLETE
- Conditional writes prevent duplicate processing
- SQS visibility timeout > Lambda timeout
- Batch size = 1 for per-object error isolation

## Tier 4: Multi-Backend / Enrichment / Redaction

```
EventBridge Scheduler → Lambda (reader) → OTel Collector / Grafana Alloy
                                              ↓
                                    Multiple backends
                                    (Grafana + Datadog + S3 archive)
```

**Additional components**:
- OTel Collector or Grafana Alloy (ECS/EC2)
- Persistent queue (Collector file-based queue)
- Routing, filtering, enrichment processors
- Multi-backend fan-out

**When to use**:
- Multiple observability backends simultaneously
- Need log enrichment (add metadata, resolve IDs)
- Need redaction (remove PII before shipping)
- Need routing (different logs to different backends)
- Vendor migration (gradual cutover)

**Reference**: See [Part 5 — OTel Collector](https://dev.to/aws-builders/escape-vendor-lock-in-multi-backend-log-delivery-with-otel-collector-for-fsx-for-ontap) for the full Collector-based architecture.

> Persistent queue behavior depends on the Collector / Alloy exporter and queue configuration. Validate retry, storage, and backpressure behavior before relying on it for stronger delivery guarantees.

## Checkpoint Strategies

| Strategy | Storage | Concurrency | Deduplication | Complexity |
|----------|---------|-------------|---------------|-----------|
| SSM high-watermark | SSM Parameter Store | Single (reserved=1) | Lexical ordering | Low |
| DynamoDB object ledger | DynamoDB | Multiple workers | Conditional writes | Medium |
| SQS message dedup | SQS FIFO | Multiple workers | Message dedup ID | Medium |

### SSM High-Watermark (Quickstart)

Stores the last successfully processed S3 key. Next run lists keys after that value. Simple, free (within SSM limits), but requires monotonically increasing keys and single-concurrency.

### DynamoDB Object Ledger (Production)

Stores per-object processing state with conditional writes:

```python
table.put_item(
    Item={"object_key": key, "etag": etag, "status": "IN_PROGRESS", "ttl": ...},
    ConditionExpression="attribute_not_exists(object_key)"
)
```

Supports concurrent workers, deduplication, retry tracking, and poison-pill detection.

## Common Failure Scenarios

| Scenario | Quickstart Behavior | Production Recommendation |
|----------|--------------------|-----------------------------|
| Vendor API 5xx | Lambda retries 3x → fails → next run retries from checkpoint | Add SQS buffer for extended outages |
| Vendor API 429 | Lambda retries with backoff → may timeout | Reduce MAX_KEYS_PER_RUN; add SQS for backpressure |
| Malformed audit file | Parse error → checkpoint stuck | Poison-pill quarantine after N retries |
| Lambda timeout | Checkpoint at last successful key | Reduce MAX_KEYS_PER_RUN or increase timeout |
| Credential rotation | 401/403 until cold start | Use auth_cache with reload-on-401/403 |
| Scheduler throttled | DLQ captures event | Next scheduled run covers the gap |

## Failure Ownership Matrix

Different failure types are owned by different layers. Understanding this separation helps assign operational responsibility:

| Failure | Owner Layer | Quickstart Behavior | Production Option |
|---------|-------------|--------------------|--------------------|
| Scheduler cannot invoke Lambda | EventBridge Scheduler | Retry + Scheduler DLQ | DLQ alarm + replay runbook |
| Lambda crashes during processing | Lambda runtime | Checkpoint not advanced; next run retries | Lambda failure destination → SQS |
| Vendor API returns 429/5xx | Shipper retry logic | Retry 3x then raise | SQS buffering or Collector path |
| One file repeatedly fails parse | Application logic | Stops checkpoint advancement | DynamoDB poison-pill ledger |
| Credential expired / rotated | Auth cache layer | 401/403 until cache refresh | auth_cache.py with reload-on-401/403 |
| Lambda concurrency exhausted | Lambda service | Throttled; Scheduler DLQ | Expected with ReservedConcurrency=1 |

## Pipeline Health Monitoring

All tiers should monitor:

| Signal | Metric | Alarm Threshold |
|--------|--------|-----------------|
| Scheduler DLQ depth | SQS `ApproximateNumberOfMessagesVisible` | > 0 |
| Lambda errors | Lambda `Errors` | > 0 |
| Lambda throttles | Lambda `Throttles` | > 0 |
| Lambda duration | Lambda `Duration` p95 | > 80% of timeout |
| Checkpoint age | Custom metric | > 2× schedule interval |
| Vendor send failures | Custom metric | > 0 |

See vendor-specific `docs/en/operations.md` for CloudWatch alarm examples.
