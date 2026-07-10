# Runbook: Checkpoint Staleness

🌐 [日本語](../../ja/runbooks/checkpoint-stale.md) | **English** (this page)

## Trigger

Custom CloudWatch Alarm: `*-checkpoint-stale` fires when the SSM Parameter Store checkpoint has not been updated for > 15 minutes (3 missed schedule intervals).

## Severity

**Warning** — Audit log processing has stopped. New files are accumulating but not being delivered.

## Diagnosis Steps

### 1. Check current checkpoint age

```bash
# Get checkpoint last modified time
aws ssm get-parameter \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --region ap-northeast-1 \
  --query 'Parameter.LastModifiedDate'

# Compare with current time — if > 15 min old, processing is stalled
```

### 2. Check if scheduler is invoking Lambda

```bash
# Recent Lambda invocations
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-<vendor>-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-1800)*1000))") \
  --region ap-northeast-1 \
  --limit 5
```

If no recent invocations: Scheduler may be disabled or throttled.

### 3. Check EventBridge Scheduler state

```bash
aws scheduler get-schedule \
  --name fsxn-<vendor>-audit-schedule \
  --region ap-northeast-1 \
  --query 'State'
```

### 4. Check if Lambda is being throttled

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=fsxn-<vendor>-integration-shipper \
  --start-time $(date -u -v-30M +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region ap-northeast-1
```

## Common Root Causes

| Cause | Symptoms | Resolution |
|-------|----------|-----------|
| Scheduler disabled | No Lambda invocations | Re-enable scheduler |
| Lambda throttled | Throttle metric > 0 | Check reserved concurrency setting |
| Lambda erroring on every file | Errors in logs, checkpoint stuck | Fix root cause (see lambda-errors runbook) |
| No new audit files | Lambda runs but nothing to process | Expected if FSx is idle; verify audit logging is enabled |
| SSM PutParameter failing | Lambda logs show SSM error | Check IAM permissions for SSM |
| Poison-pill file blocking | Same file fails repeatedly | Manually advance checkpoint (see DLQ replay runbook) |

## Resolution

### Scheduler Disabled

```bash
aws scheduler update-schedule \
  --name fsxn-<vendor>-audit-schedule \
  --state ENABLED \
  --schedule-expression "rate(5 minutes)" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target <existing-target-config> \
  --region ap-northeast-1
```

### Lambda Throttled

```bash
# Check current concurrency setting
aws lambda get-function-concurrency \
  --function-name fsxn-<vendor>-integration-shipper \
  --region ap-northeast-1

# If set to 0 (disabled), restore to 1
aws lambda put-function-concurrency \
  --function-name fsxn-<vendor>-integration-shipper \
  --reserved-concurrent-executions 1 \
  --region ap-northeast-1
```

### No New Audit Files (Expected)

If FSx for ONTAP has no file activity, no new audit files are generated. This is normal for idle systems. Verify:

```bash
# List recent files via S3 AP
aws s3api list-objects-v2 \
  --bucket <s3-ap-arn> \
  --prefix "audit/" \
  --max-keys 5 \
  --query 'Contents | sort_by(@, &LastModified) | [-5:].[Key, LastModified]'
```

If the latest file matches the checkpoint, the system is healthy — just idle.

## Verification

After resolution:
1. Wait for next scheduled invocation (5 min)
2. Confirm checkpoint timestamp updates
3. Confirm alarm returns to OK state
4. Verify logs arriving in vendor platform

## Escalation

If checkpoint remains stale > 1 hour:
- Check Scheduler DLQ for failed invocations
- Review Lambda error logs (see lambda-errors runbook)
- Verify FSx for ONTAP audit logging is still enabled
- Contact pipeline owner
