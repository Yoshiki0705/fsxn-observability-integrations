# Runbook: DLQ Replay

## Trigger

CloudWatch Alarm: `*-dlq-depth` fires when `ApproximateNumberOfMessagesVisible > 0` for the Scheduler DLQ or Lambda failure destination.

## Severity

**Warning** — Data delivery is delayed but not lost. Messages are preserved in the DLQ for 14 days.

## Diagnosis Steps

### 1. Identify the failed messages

```bash
# Check DLQ depth
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessagesVisible \
  --region ap-northeast-1

# Peek at messages (does not delete)
aws sqs receive-message \
  --queue-url <dlq-url> \
  --max-number-of-messages 5 \
  --visibility-timeout 0 \
  --region ap-northeast-1
```

### 2. Check if auto-recovery occurred

The poller uses a checkpoint — the next scheduled run may have already retried:

```bash
# Check current checkpoint
aws ssm get-parameter \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --region ap-northeast-1

# Compare with DLQ message payload (contains the scheduler input)
# If checkpoint has advanced past the DLQ message's key range, auto-recovered
```

### 3. Check Lambda logs for root cause

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-<vendor>-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-3600)*1000))") \
  --filter-pattern "ERROR" \
  --region ap-northeast-1
```

## Common Root Causes

| Cause | Symptoms | Resolution |
|-------|----------|-----------|
| Vendor API outage | HTTP 5xx in Lambda logs | Wait for vendor recovery; messages auto-retry on next schedule |
| Vendor rate limiting | HTTP 429 in Lambda logs | Reduce MAX_KEYS_PER_RUN; add backoff |
| Invalid credentials | HTTP 401/403 in Lambda logs | Rotate secret in Secrets Manager |
| Lambda timeout | "Task timed out" in logs | Increase timeout or reduce MAX_KEYS_PER_RUN |
| Malformed audit file | Parse error in logs | Poison-pill — skip file, advance checkpoint manually |
| S3 AP access denied | AccessDenied in logs | Check IAM + S3 AP policy + network path |

## Resolution: Manual Replay

If auto-recovery did NOT occur (checkpoint has not advanced):

```bash
# Option A: Let the next scheduled run retry automatically
# (Default behavior — just wait for next 5-min interval)

# Option B: Manual invoke with the DLQ payload
aws sqs receive-message \
  --queue-url <dlq-url> \
  --max-number-of-messages 1 \
  --region ap-northeast-1 > /tmp/dlq-msg.json

# Extract the payload and invoke Lambda
PAYLOAD=$(cat /tmp/dlq-msg.json | jq -r '.Messages[0].Body')
aws lambda invoke \
  --function-name fsxn-<vendor>-integration-shipper \
  --payload "$PAYLOAD" \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 \
  /tmp/replay-response.json

# Verify success
cat /tmp/replay-response.json

# Delete the DLQ message after successful replay
RECEIPT=$(cat /tmp/dlq-msg.json | jq -r '.Messages[0].ReceiptHandle')
aws sqs delete-message \
  --queue-url <dlq-url> \
  --receipt-handle "$RECEIPT" \
  --region ap-northeast-1
```

## Resolution: Poison-Pill (Bad File)

If a specific audit file repeatedly fails parsing:

```bash
# 1. Identify the problematic file from Lambda logs
# Look for: "Failed to parse: audit/svm-prod-01/2026/01/15/audit-corrupt.json"

# 2. Manually advance the checkpoint past the bad file
aws ssm put-parameter \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --value "audit/svm-prod-01/2026/01/15/audit-corrupt.json" \
  --type String \
  --overwrite \
  --region ap-northeast-1

# 3. Delete the DLQ message
aws sqs purge-queue --queue-url <dlq-url> --region ap-northeast-1

# 4. Document the skipped file for investigation
```

## Verification

After resolution:
1. Confirm DLQ depth returns to 0
2. Confirm checkpoint is advancing on next scheduled run
3. Confirm logs are arriving in the vendor platform
4. Clear the CloudWatch alarm

## Escalation

If the issue persists after 30 minutes:
- Check AWS Health Dashboard for regional issues
- Check vendor status page for API outages
- Contact the pipeline owner (see operational-guide.md)

## Prevention

- Monitor DLQ depth with CloudWatch alarm (already configured)
- Set up vendor API health checks
- Review Lambda error rate weekly
- Test DLQ replay procedure quarterly
