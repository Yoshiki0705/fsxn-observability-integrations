# Runbook: Lambda Errors Alarm

🌐 [日本語](../../ja/runbooks/lambda-errors.md) | **English** (this page)

## Trigger

CloudWatch Alarm: `*-lambda-errors` fires when Lambda Errors > 5 in 10 minutes.

## Severity

**Warning** — Pipeline delivery is degraded. Some audit logs may be delayed.

## Diagnosis Steps

### 1. Check Lambda error logs

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-<vendor>-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-1800)*1000))") \
  --filter-pattern "ERROR" \
  --region ap-northeast-1 \
  --limit 20
```

### 2. Identify error pattern

| Error Pattern | Likely Cause | Resolution |
|--------------|-------------|-----------|
| `Task timed out after X seconds` | Lambda timeout | Increase timeout or reduce MAX_KEYS_PER_RUN |
| `AccessDenied` on S3 | IAM or S3 AP policy | Verify IAM role + S3 AP resource policy |
| `HTTP 401` / `HTTP 403` | Vendor credential expired | Rotate secret in Secrets Manager |
| `HTTP 429` | Vendor rate limiting | Reduce batch size, add backoff |
| `HTTP 5xx` | Vendor API outage | Wait; check vendor status page |
| `ConnectionError` / `Timeout` | Network issue | Check VPC config, NAT Gateway, security groups |
| `JSONDecodeError` / `ParseError` | Malformed audit file | Poison-pill — see DLQ Replay runbook |
| `ResourceNotFoundException` | SSM parameter or secret deleted | Recreate the missing resource |

### 3. Check if DLQ has messages

```bash
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessagesVisible
```

If DLQ has messages, follow the [DLQ Replay Runbook](dlq-replay.md).

## Resolution by Root Cause

### Vendor Credential Expired

```bash
# Update the secret value
aws secretsmanager update-secret \
  --secret-id <vendor>/fsxn-credentials \
  --secret-string '{"api_key":"<new-key>"}' \
  --region ap-northeast-1
```

The Lambda will pick up the new credential on next cold start (within minutes).

### Lambda Timeout

```bash
# Reduce processing per invocation
aws lambda update-function-configuration \
  --function-name fsxn-<vendor>-integration-shipper \
  --environment "Variables={MAX_KEYS_PER_RUN=50,SAFETY_THRESHOLD_MS=45000}" \
  --region ap-northeast-1
```

### Network Issue (VPC Lambda)

Check:
1. Security group allows outbound HTTPS (port 443)
2. NAT Gateway is healthy (if Lambda needs internet access)
3. S3 Gateway Endpoint exists (if accessing S3 AP from VPC)

### Vendor API Outage

1. Check vendor status page
2. Errors will auto-resolve when vendor recovers
3. DLQ preserves failed scheduler invocations for replay
4. Next scheduled run will retry from checkpoint

## Verification

After resolution:
1. Wait for next scheduled invocation (5 min)
2. Confirm Lambda succeeds (no errors in logs)
3. Confirm checkpoint advances
4. Confirm alarm returns to OK state

## Escalation

If errors persist > 1 hour after resolution attempt:
- Review CloudWatch Logs Insights for error trends
- Check AWS Health Dashboard for regional issues
- Contact pipeline owner
