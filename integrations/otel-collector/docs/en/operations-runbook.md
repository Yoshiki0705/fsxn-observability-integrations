# Operations Runbook

🌐 [日本語](../ja/operations-runbook.md) | **English** (this page)

## 4-Layer Health Model

All operational scenarios are diagnosed using this layered model:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Producer (Lambda)                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Generates OTLP logs from ONTAP telemetry sources        │    │
│  │  Monitor: CloudWatch Lambda metrics                      │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Collector Process                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Receives, processes, and routes OTLP logs               │    │
│  │  Monitor: health_check + internal metrics                │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Exporter                                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Delivers logs to each backend                           │    │
│  │  Monitor: otelcol_exporter_* metrics                     │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Backend                                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Ingests, indexes, and serves queries                    │    │
│  │  Monitor: Backend-specific dashboards                    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

| Layer | What to Monitor | Key Metrics |
|-------|----------------|-------------|
| Producer (Lambda) | Errors, duration, retry count | CloudWatch Lambda metrics |
| Collector process | OTLP receiver, memory, CPU | health_check + internal metrics |
| Exporter | Error count, retry count, queue length | otelcol_exporter_* metrics |
| Backend | Last successful ingest, event count, latency | Backend-specific dashboards |

---

## Runbook Entry 1: Collector Unavailable

### Symptom
- Lambda receives connection refused or timeout when sending OTLP
- Health check endpoint (`http://<collector>:13133/`) returns non-200 or times out
- No new logs appearing in any backend

### Detection
- CloudWatch Alarm: `otel-collector-unhealthy`
- Lambda error logs: `ConnectionRefusedError` or `TimeoutError`
- ECS task status: STOPPED or PENDING

### Impact
- **All backends** stop receiving new logs
- Lambda retries exhaust → events sent to DLQ
- Data gap duration = time to recovery

### Resolution Steps

```bash
# 1. Check ECS task status
aws ecs describe-services \
  --cluster fsxn-otel \
  --services otel-collector \
  --query "services[0].{desired:desiredCount,running:runningCount,events:events[:3]}"

# 2. Check task stopped reason
aws ecs list-tasks --cluster fsxn-otel --service-name otel-collector --desired-status STOPPED
aws ecs describe-tasks --cluster fsxn-otel --tasks <task-arn> \
  --query "tasks[0].{reason:stoppedReason,exitCode:containers[0].exitCode}"

# 3. Force new deployment
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment

# 4. Verify recovery
watch -n 5 'curl -sf http://<collector>:13133/ && echo OK || echo FAIL'

# 5. Reprocess DLQ after recovery
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages
```

### Prevention
- ECS restart policy with exponential backoff
- Multi-AZ deployment for high availability
- Persistent queue (file_storage extension) to survive restarts

---

## Runbook Entry 2: Backend Exporter Failing (One Backend)

### Symptom
- One backend stops receiving logs; others continue normally
- Collector internal metrics show exporter errors for specific backend
- No Lambda errors (Collector is healthy)

### Detection
- Metric: `otelcol_exporter_send_failed_log_records{exporter="otlp_http/<backend>"}` > 0
- Metric: `otelcol_exporter_queue_size{exporter="otlp_http/<backend>"}` growing
- Backend-specific dashboard shows gap

### Impact
- **Single backend** affected; other backends unaffected
- Queue absorbs short outages (minutes)
- Extended outage → queue full → data dropped for that backend only

### Resolution Steps

```bash
# 1. Identify failing exporter
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_send_failed_log_records'

# 2. Check exporter queue status
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_queue_size'

# 3. Check backend status (vendor-specific)
# Datadog: https://status.datadoghq.com/
# Grafana: https://status.grafana.com/
# Honeycomb: https://status.honeycomb.io/

# 4. If backend is down, wait for recovery (queue handles short outages)
# If backend is up but rejecting, check credentials:
aws secretsmanager get-secret-value \
  --secret-id fsxn-otel-<backend>-api-key \
  --query "VersionIdsToStages"

# 5. If credentials expired, rotate and restart
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment
```

### Prevention
- Per-exporter `sending_queue` with adequate `queue_size`
- `retry_on_failure` with reasonable `max_elapsed_time`
- Backend status page monitoring
- Credential rotation alerts (30 days before expiry)

---

## Runbook Entry 3: Queue Growing / Backpressure

### Symptom
- Exporter queue size steadily increasing
- Collector memory usage rising
- Potential `memory_limiter` triggering (receiver starts refusing data)

### Detection
- Metric: `otelcol_exporter_queue_size` > 80% of `queue_size` config
- Metric: `otelcol_processor_refused_log_records` > 0 (memory_limiter active)
- CloudWatch: ECS task memory utilization > 80%

### Impact
- If queue fills: new events for that exporter are dropped
- If memory_limiter triggers: Lambda receives 503 → retries → DLQ
- Cascading effect possible if multiple exporters queue simultaneously

### Resolution Steps

```bash
# 1. Identify which exporter(s) are queuing
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_queue_size'

# 2. Check if backend is slow or down
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_send_latency'

# 3. If backend is slow: temporarily increase batch timeout
# Edit config and redeploy (or use config reload if supported)

# 4. If sustained: scale Collector horizontally
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --desired-count 2

# 5. If critical: temporarily disable non-essential exporters
# Remove the slow exporter from pipeline, redeploy
# Reprocess missed data from DLQ after recovery
```

### Prevention
- Set `queue_size` based on expected burst duration × event rate
- Configure `memory_limiter` with appropriate limits
- Auto-scaling based on CPU/memory thresholds
- Persistent queue (`file_storage`) for critical exporters

---

## Runbook Entry 4: Lambda Cannot Reach Collector

### Symptom
- Lambda logs show connection timeout to Collector endpoint
- Lambda duration at maximum (timeout)
- Events accumulating in DLQ

### Detection
- CloudWatch: Lambda Duration = Timeout value
- CloudWatch: Lambda Errors increasing
- Lambda logs: `ConnectTimeoutError: Connect timeout on endpoint URL`

### Impact
- No telemetry delivered to any backend
- DLQ accumulates events (reprocessable after fix)
- Audit log processing falls behind

### Resolution Steps

```bash
# 1. Verify Collector is running and healthy
curl -sf http://<collector>:13133/ && echo "Collector OK" || echo "Collector DOWN"

# 2. Check security group rules
aws ec2 describe-security-groups \
  --group-ids <collector-sg-id> \
  --query "SecurityGroups[0].IpPermissions[?ToPort==\`4318\`]"

# 3. Check VPC connectivity (if Lambda is in VPC)
# Ensure Lambda subnet can route to Collector subnet
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<lambda-subnet-id>"

# 4. Check Collector endpoint configuration in Lambda env vars
aws lambda get-function-configuration \
  --function-name fsxn-otel-integration-shipper \
  --query "Environment.Variables.OTEL_COLLECTOR_ENDPOINT"

# 5. If DNS issue: verify service discovery or endpoint resolution
# If network issue: check NACLs, route tables, NAT Gateway

# 6. After fix: reprocess DLQ
aws lambda invoke \
  --function-name fsxn-otel-dlq-reprocessor \
  --payload '{"source": "manual"}' \
  /dev/null
```

### Prevention
- Lambda and Collector in same VPC/subnet when possible
- Health check alarm triggers before Lambda timeout
- Endpoint connectivity test in Lambda cold start (fail fast)
- VPC Flow Logs enabled for network debugging

---

## Runbook Entry 5: Data Missing in One Backend Only

### Symptom
- One backend shows fewer events than others for the same time range
- No exporter errors in Collector metrics
- Other backends have complete data

### Detection
- Cross-backend event count comparison (daily reconciliation)
- Backend-specific query returns fewer results than expected
- No corresponding exporter errors in Collector metrics

### Impact
- Single backend has incomplete data
- May affect alerting or dashboards on that backend
- Compliance risk if the affected backend is used for audit

### Resolution Steps

```bash
# 1. Check if filtering is applied per-exporter
grep -A 10 'processors:' otel-collector-config.yaml

# 2. Check backend-specific timestamp rejection
# Grafana/Loki: events older than reject_old_samples_max_age are silently dropped
# Datadog: events older than 18 hours are rejected

# 3. Check for backend-side rate limiting
# Look for HTTP 429 responses in Collector debug logs
docker logs otel-collector 2>&1 | grep -i "429\|rate.limit\|too.many"

# 4. Check backend ingestion pipeline
# Verify index/dataset exists and is accepting data
# Check backend-side processing rules (exclusion filters, sampling)

# 5. If timestamp issue: adjust Lambda to use current time as fallback
# If rate limit: reduce batch size or add jitter

# 6. Backfill missing data from S3 source
# Re-invoke Lambda for the affected time range
```

### Prevention
- Understand each backend's timestamp acceptance window
- Monitor backend-side ingestion metrics
- Daily automated reconciliation across all backends
- Use ONTAP timestamp (not ingest time) as primary event time

---

## Runbook Entry 6: Config Rollback Needed

### Symptom
- Recent config change caused unexpected behavior
- Events not routing correctly after deployment
- Exporter errors started after config update

### Detection
- Correlation: issues started after last deployment
- Git log shows recent config change
- Collector logs show config validation errors

### Impact
- Depends on the change: routing errors, missing data, or complete failure
- Duration = time to detect + time to rollback

### Resolution Steps

```bash
# 1. Identify the problematic commit
git log --oneline -5 -- \
  'integrations/otel-collector/otel-collector-config*.yaml'

# 2. Revert to last known good config
git revert <problematic-commit>
# OR
git checkout <last-good-commit> -- \
  'integrations/otel-collector/otel-collector-config.yaml'

# 3. Validate the reverted config
docker run --rm \
  -v $(pwd)/integrations/otel-collector/otel-collector-config.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector-contrib:0.152.0 \
  validate --config /etc/otelcol/config.yaml

# 4. Deploy the rollback
git commit -m "fix: rollback Collector config to last known good state"
git push origin main
# CI/CD deploys automatically, or:
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment

# 5. Verify recovery
curl -sf http://<collector>:13133/ && echo "Healthy"
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_send_failed_log_records'

# 6. Reprocess any DLQ messages from the incident window
```

### Prevention
- CI validation of config before deployment (`validate` command)
- Staged rollout (canary → full)
- Config change requires PR review + approval
- Automated rollback on health check failure (ECS deployment circuit breaker)

---

## Runbook Entry 7: Emergency Direct-Send Bypass

### Symptom
- Collector is down and cannot be recovered quickly
- Critical telemetry (audit logs, security events) must continue flowing
- DLQ is filling up and approaching retention limits

### Detection
- Collector unavailable for > 30 minutes
- DLQ message count growing beyond acceptable threshold
- Business-critical monitoring is blind

### Impact
- Temporary loss of multi-backend fan-out
- Single backend receives data (chosen by priority)
- Config divergence until Collector is restored

### Resolution Steps

```bash
# 1. Identify the highest-priority backend
# Typically: SIEM for security events, primary observability for audit

# 2. Update Lambda environment to bypass Collector
aws lambda update-function-configuration \
  --function-name fsxn-otel-integration-shipper \
  --environment "Variables={
    DELIVERY_MODE=direct,
    DIRECT_SEND_ENDPOINT=https://<backend-endpoint>,
    DIRECT_SEND_API_KEY_SECRET_ARN=arn:aws:secretsmanager:<region>:123456789012:secret:fsxn-<backend>-api-key
  }"

# 3. Verify direct send is working
aws logs tail /aws/lambda/fsxn-otel-integration-shipper --since 5m \
  | grep -i "direct.send\|success\|error"

# 4. Process DLQ backlog
aws lambda invoke \
  --function-name fsxn-otel-dlq-reprocessor \
  --payload '{"mode": "direct", "target": "<backend>"}' \
  /dev/null

# 5. After Collector recovery: revert to normal mode
aws lambda update-function-configuration \
  --function-name fsxn-otel-integration-shipper \
  --environment "Variables={
    DELIVERY_MODE=collector,
    OTEL_COLLECTOR_ENDPOINT=http://<collector>:4318
  }"

# 6. Reconcile: identify events that only went to one backend
# Backfill other backends from S3 source if needed
```

### Prevention
- Lambda supports dual-mode (collector + direct) with env var switch
- Pre-configured direct-send credentials in Secrets Manager
- Runbook rehearsal quarterly
- Collector HA deployment (multi-AZ, auto-scaling)

---

## Quick Reference: Diagnosis Flow

```
Issue detected
     │
     ▼
┌─────────────────────────────────┐
│ Is Collector health check OK?   │
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 1 (Collector Unavailable)
     │
     ▼
┌─────────────────────────────────┐
│ Are all exporters sending OK?   │
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 2 (Backend Failing)
     │                  or Runbook 3 (Queue Growing)
     ▼
┌─────────────────────────────────┐
│ Is Lambda sending to Collector? │
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 4 (Lambda Cannot Reach)
     │
     ▼
┌─────────────────────────────────┐
│ Is data present in all backends?│
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 5 (Missing in One Backend)
     │
     ▼
  System healthy ✅
```
