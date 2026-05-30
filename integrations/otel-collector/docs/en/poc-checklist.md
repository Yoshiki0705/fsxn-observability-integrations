# PoC Checklist: OTel Collector Integration

## 5-Phase PoC Structure

```
Phase 1          Phase 2              Phase 3             Phase 4        Phase 5
Direct Send  →  Introduce Collector  →  Parallel Delivery  →  Compare  →  Cut Over
(baseline)      (shadow mode)           (dual write)         (validate)    (production)
```

## Preconditions Checklist

Before starting the PoC, confirm all preconditions are met:

- [ ] FSx for ONTAP audit logging is enabled and producing logs to S3
- [ ] S3 Access Point is configured and accessible from Lambda
- [ ] At least one backend account is provisioned (Grafana/Honeycomb/Datadog)
- [ ] Docker environment available for local Collector testing
- [ ] AWS credentials with permissions to deploy Lambda + ECS/Fargate
- [ ] Network path confirmed: Lambda → Collector endpoint (port 4318)
- [ ] Secrets Manager secrets created for backend credentials
- [ ] Baseline event volume measured (events/day)
- [ ] Success criteria agreed upon by stakeholders

## Phase 1: Direct Send (Baseline)

**Goal**: Establish baseline metrics with existing direct-send Lambda.

### Success Criteria

- [ ] Lambda delivers logs to primary backend successfully
- [ ] Baseline latency measured (Lambda invoke → backend arrival)
- [ ] Baseline error rate recorded (< 0.1% target)
- [ ] Event count per day documented
- [ ] All required attributes present in backend

### Actions

```bash
# Measure baseline delivery latency
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=fsxn-<vendor>-log-shipper \
  --start-time $(date -u -v-1d +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average p99
```

## Phase 2: Introduce Collector (Shadow Mode)

**Goal**: Deploy OTel Collector without affecting production traffic.

### Success Criteria

- [ ] Collector health check passes (`curl http://<collector>:13133/`)
- [ ] Collector accepts OTLP payloads on port 4318
- [ ] Collector exports to at least one backend successfully
- [ ] No impact on existing direct-send Lambda

### Actions

```bash
# Deploy Collector (ECS Fargate)
aws cloudformation deploy \
  --template-file template-collector.yaml \
  --stack-name fsxn-otel-collector-poc \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1

# Verify health
curl -f http://<collector-endpoint>:13133/

# Send test payload
bash scripts/generate-otlp-payload.sh --output /tmp/test.json
curl -X POST http://<collector-endpoint>:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d @/tmp/test.json
```

## Phase 3: Parallel Delivery (Dual Write)

**Goal**: Run both direct-send and Collector paths simultaneously.

### Success Criteria

- [ ] Both paths deliver the same events to their respective backends
- [ ] No duplicate events within a single path
- [ ] Collector path latency within 2x of direct-send baseline
- [ ] Zero data loss over 24-hour observation period
- [ ] Collector exporter error count = 0

### Actions

```bash
# Deploy OTel Lambda alongside existing Lambda
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration-poc \
  --parameter-overrides \
    OtlpEndpoint=http://<collector-endpoint>:4318 \
    S3BucketName=<audit-bucket> \
  --capabilities CAPABILITY_IAM

# Configure EventBridge to trigger both Lambdas
# (existing rule continues, new rule added for OTel Lambda)
```

## Phase 4: Compare (Validate)

**Goal**: Confirm data parity between direct-send and Collector paths.

### Data Parity Check Method

```bash
# 1. Query event count from direct-send backend (e.g., Datadog)
#    Filter: service:fsxn-audit, last 24h → count

# 2. Query event count from Collector backend (e.g., Grafana)
#    Filter: {job="fsxn-audit"}, last 24h → count

# 3. Compare counts (tolerance: ±1%)
```

### Backend Parity Verification Matrix

| Check | Datadog | Grafana Cloud | Honeycomb |
|-------|---------|---------------|-----------|
| Event count matches source | ✅ | ✅ | ✅ |
| `service.name` visible/searchable | ✅ | ✅ | ✅ |
| `fsxn.svm` searchable | ✅ | ✅ | ✅ |
| `fsxn.operation` searchable | ✅ | ✅ | ✅ |
| `severityText` visible | ✅ | ✅ | ✅ |
| Timestamp accepted (< 18h old) | ✅ | ✅ | ✅ |
| `user.name` searchable | ✅ | ✅ | ✅ |
| `client.address` searchable | ✅ | ✅ | ✅ |

> **Note**: While OTLP standardizes the wire format, each backend may differ in:
> - How resource attributes are indexed and displayed
> - Severity level handling and visualization
> - Timestamp acceptance windows
> - Query syntax for searching attributes
> - Default retention periods
> - Ingestion delay (seconds to minutes)

### Success Criteria

- [ ] Event count difference < 1% between paths
- [ ] All required attributes present in Collector-delivered logs
- [ ] Timestamp accuracy within 1 second
- [ ] No attribute mapping errors
- [ ] Collector path p99 latency acceptable (< 10s end-to-end)

### Comparison Checklist

| Metric | Direct Send | Collector Path | Pass? |
|--------|-------------|----------------|-------|
| Events/day | ___ | ___ | ±1% |
| p50 latency | ___ ms | ___ ms | < 2x |
| p99 latency | ___ ms | ___ ms | < 3x |
| Error rate | ___ % | ___ % | < 0.1% |
| Attribute completeness | ___ / ___ | ___ / ___ | 100% |

## Phase 5: Cut Over (Production)

**Goal**: Switch production traffic to Collector path.

### Success Criteria

- [ ] All production traffic flows through Collector
- [ ] Direct-send Lambda disabled (not deleted)
- [ ] Monitoring confirms stable delivery for 48+ hours
- [ ] Rollback tested and documented
- [ ] Old Lambda retained for 14 days before deletion

### Actions

```bash
# 1. Disable direct-send EventBridge rule
aws events disable-rule \
  --name fsxn-<vendor>-s3-trigger \
  --region ap-northeast-1

# 2. Monitor Collector path for 48 hours
# 3. If stable, proceed to cleanup
# 4. If issues, execute rollback
```

## Rollback Procedure

### Immediate Rollback (< 5 minutes)

```bash
# 1. Re-enable direct-send rule
aws events enable-rule \
  --name fsxn-<vendor>-s3-trigger \
  --region ap-northeast-1

# 2. Disable OTel Lambda rule
aws events disable-rule \
  --name fsxn-otel-s3-trigger \
  --region ap-northeast-1

# 3. Verify direct-send Lambda is processing
aws logs tail /aws/lambda/fsxn-<vendor>-log-shipper --since 2m
```

### Full Rollback

```bash
# 1. Re-enable direct-send (as above)
# 2. Delete OTel stack (optional, can keep for retry)
aws cloudformation delete-stack \
  --stack-name fsxn-otel-integration-poc

# 3. Document failure reason for post-mortem
```

## Go/No-Go Criteria

| Criteria | Threshold | Measured | Go? |
|----------|-----------|----------|-----|
| Data parity (event count) | ±1% | ___ | ☐ |
| End-to-end latency (p99) | < 10s | ___ | ☐ |
| Error rate | < 0.1% | ___ | ☐ |
| Collector uptime (7-day) | > 99.9% | ___ | ☐ |
| Attribute completeness | 100% | ___ | ☐ |
| Rollback tested | Yes | ___ | ☐ |
| Stakeholder sign-off | Yes | ___ | ☐ |
| Cost delta acceptable | < 20% increase | ___ | ☐ |

**Decision**: All criteria must be "Go" to proceed with production cutover. Any single "No-Go" requires remediation before retry.

## Executive Go/No-Go Criteria

For enterprise and partner-led deployments, add these governance criteria:

| Criterion | Go | No-Go |
|-----------|-----|-------|
| Backend parity | Event count and critical fields match across selected backends | Material field loss or unexplained count mismatch |
| Operations ownership | Collector owner and change process defined | No clear owner |
| Rollback | Direct-send or previous exporter path documented and tested | No rollback path |
| Security | Secrets, network boundary, and access control reviewed | Shared credentials or public Collector endpoint |
| Compliance | Raw audit evidence retention defined separately from backend copies | Normalized logs treated as sole evidence without approval |
| Change management | Collector config changes follow approval process | Ad-hoc config changes without review |