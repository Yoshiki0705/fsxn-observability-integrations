# Content Classification Scanner Demo Runbook

🌐 [日本語](../ja/demo-content-classification.md) | **English** (this page)

## Purpose

Step-by-step procedure for demonstrating the Content-Level PII Classification Scanner end-to-end. Covers: deploy → upload a synthetic PII sample → invoke the scanner → confirm the DynamoDB report → confirm the SNS notification → clean up.

Use this runbook for:
- Live demos (in-person or recorded)
- E2E verification before blog publication
- Internal training

> **Evidence format note**: This runbook describes, after each step, what a successful result looks like ("what to check for") in plain language, rather than a screenshot placeholder or a fabricated sample output block. As of this writing, this specific runbook has not been executed end-to-end and no real screenshots or command output have been captured for it — do not treat anything shown in this guide as evidence that these steps have actually been run. When you do execute this runbook, capture your own real command output or screenshots (masking account IDs/IPs/ARNs per `docs/screenshots/mask_screenshots.py`) and record them, following the format used in `docs/screenshots/automated-response/e2e-verification-results.md` for the [Automated Response Guide](automated-response-guide.md).

---

## Prerequisites

| Item | Requirement |
|------|------------|
| S3 Access Point | An existing S3 Access Point for an FSx for ONTAP volume — Internet-origin for Deploy Mode 1, VPC-scoped for Deploy Mode 2 (see [Content Classification Scanner](content-classification-scanner.md#an-existing-s3-access-point)) |
| Write access | The access point (or a separate one on the same volume) must allow `PutObject`, to upload the synthetic test file — a read-only access point will reject the upload |
| AWS CLI | Configured with appropriate IAM permissions (`cloudformation:*`, `lambda:InvokeFunction`, `dynamodb:GetItem`, `s3:PutObject`/`DeleteObject` against the access point) |
| jq | Installed for JSON formatting (optional, used for readability in a few steps) |

---

## Phase 1: Deploy the Scanner Stack

This runbook uses **Deploy Mode 1 (Standalone, Internet-Origin Access Point)** — the simpler of the two modes described in [Content Classification Scanner § Deployment](content-classification-scanner.md#deployment). If your access point is VPC-scoped (for example, one produced by the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s `AttachAccessPoint` step), use Deploy Mode 2 instead — see that guide's own deployment parameters.

### Step 1.1: Confirm Your Access Point's Network Origin

```bash
aws s3control get-access-point \
  --account-id <account-id> \
  --name <access-point-name> \
  --query NetworkOrigin
```

**What to check**: the output is `"Internet"` for Deploy Mode 1 below. If it's `"VPC"`, switch to Deploy Mode 2 (set `VpcId`/`SubnetIds`/`SecurityGroupId`/`RouteTableIds` per the guide's Deployment section) — Mode 1 will fail deterministically against a VPC-scoped access point regardless of IAM permissions.

### Step 1.2: Deploy CloudFormation (Mode 1)

```bash
aws cloudformation deploy \
  --template-file shared/templates/content-classification-scanner.yaml \
  --stack-name fsxn-content-classification \
  --parameter-overrides \
    DefaultLanguageCode=en \
    DefaultMaxFiles=500 \
    NotificationTopicArn=<optional-sns-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 1.3: Verify Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-content-classification \
  --query 'Stacks[0].Outputs' \
  --output table
```

**What to check**: the output table includes `ScannerFunctionArn`, `ReportTableName`, and `InvokeExample` keys, each with a non-empty value.

### Step 1.4: Set CLI Environment

```bash
export SCANNER_FUNCTION=$(aws cloudformation describe-stacks \
  --stack-name fsxn-content-classification \
  --query 'Stacks[0].Outputs[?OutputKey==`ScannerFunctionArn`].OutputValue' \
  --output text)

export REPORT_TABLE=$(aws cloudformation describe-stacks \
  --stack-name fsxn-content-classification \
  --query 'Stacks[0].Outputs[?OutputKey==`ReportTableName`].OutputValue' \
  --output text)

export ACCESS_POINT_ARN="<your-access-point-arn>"
echo "Scanner: $SCANNER_FUNCTION"
echo "Report table: $REPORT_TABLE"
```

---

## Phase 2: Demonstrate PII Discovery

This phase follows the same sequence as [Content Classification Scanner § Quick Validation](content-classification-scanner.md#quick-validation) — see that section for the exact commands this project's own development-time verification used.

### Step 2.1: Confirm Baseline (No Findings Expected Yet)

If this is the first scan against this access point, you can skip straight to Step 2.2. If you've scanned this access point before, note the current `files_with_pii` value in the ledger for comparison later:

```bash
aws dynamodb query \
  --table-name "$REPORT_TABLE" \
  --key-condition-expression "access_point_arn = :arn" \
  --expression-attribute-values "{\":arn\": {\"S\": \"$ACCESS_POINT_ARN\"}}" \
  --query 'Items[*].{started_at: started_at.S, files_with_pii: files_with_pii.N}' \
  --output table
```

**What to check**: a list of prior scan runs (if any) for this access point, each with its own `started_at` and `files_with_pii` count. This is your "before" baseline.

### Step 2.2: Create a Synthetic PII Test File

```bash
cat > /tmp/pii-test-sample.txt <<'EOF'
Customer Support Ticket #48213
Name: John Sample Doe
Email: john.sample.doe@example.com
Phone: 555-0142-9981
SSN: 078-05-1120
Address: 123 Example Street, Springfield, IL 62704
EOF
```

**What to check**: the file exists at `/tmp/pii-test-sample.txt`. This is synthetic data — no real personal information — safe to upload and delete as part of this demo.

### Step 2.3: Upload the Test File Through the Access Point

```bash
aws s3api put-object \
  --bucket "$ACCESS_POINT_ARN" \
  --key validation/pii-test-sample.txt \
  --body /tmp/pii-test-sample.txt
```

**What to check**: the command completes without error and returns an `ETag`. If it fails with `AccessDenied`, confirm the access point (or the underlying volume's export policy / S3 resource policy) actually grants write access — a read-only access point will reject this.

### Step 2.4: Invoke the Scanner

```bash
aws lambda invoke \
  --function-name "$SCANNER_FUNCTION" \
  --payload "{\"access_point_arn\":\"$ACCESS_POINT_ARN\",\"max_files\":50}" \
  --cli-binary-format raw-in-base64-out \
  /tmp/scan-response.json

cat /tmp/scan-response.json
```

**What to check**: the invocation returns `StatusCode: 200` (in the `aws lambda invoke` command's own output, not the payload), and `/tmp/scan-response.json` contains a JSON report with `files_scanned`, `files_with_pii`, and a `started_at` timestamp. Note the `started_at` value — you'll need it in the next step.

### Step 2.5: Confirm the Finding Landed in the Ledger

```bash
export STARTED_AT="<started_at value from the previous step's response>"

aws dynamodb get-item \
  --table-name "$REPORT_TABLE" \
  --key "{\"access_point_arn\":{\"S\":\"$ACCESS_POINT_ARN\"},\"started_at\":{\"S\":\"$STARTED_AT\"}}"
```

**What to check**: the item exists and `files_with_pii` is `1` or more (it will be 1 if `pii-test-sample.txt` is the only scannable file with PII under this access point, or higher if other pre-existing files also contain PII-shaped content). The `findings` list should include an entry for `validation/pii-test-sample.txt` with entity types such as `NAME`, `EMAIL`, `PHONE`, `SSN`, and `ADDRESS` — see [Content Classification Scanner § Quick Validation](content-classification-scanner.md#quick-validation) for the expected confidence-score ranges per entity type. Confirm the matched PII values themselves are **not** present anywhere in this item — only entity type, count, and confidence score (this is the scanner's data-minimization design; see [Entity Aggregation](content-classification-scanner.md#entity-aggregation--data-minimization-by-design)).

### Step 2.6: Confirm the SNS Notification (If Configured)

Skip this step if you deployed without `NotificationTopicArn`.

**What to check**: an email or other subscriber endpoint received a notification referencing this scan. If you'd rather not rely on an email screenshot as evidence, the Lambda logs the same notification attempt — check CloudWatch Logs for this function for a log line confirming the publish, or a `"Notification failed"` warning if delivery failed silently (see the [SNS-delivery note](content-classification-scanner.md#testing) in the guide's Testing section for why a failed publish never surfaces as a Lambda error).

---

## Phase 3: Demonstrate the "No PII Found" and Troubleshooting Paths

### Step 3.1: Scan a Directory With No PII

Invoke the scanner against a path (or a fresh access point) you know does not contain PII-shaped content:

```bash
aws lambda invoke \
  --function-name "$SCANNER_FUNCTION" \
  --payload "{\"access_point_arn\":\"$ACCESS_POINT_ARN\",\"max_files\":50}" \
  --cli-binary-format raw-in-base64-out \
  /tmp/scan-response-clean.json

cat /tmp/scan-response-clean.json
```

**What to check**: `files_with_pii` is `0`, and `files_scanned` is greater than `0` (confirming the scan actually ran against files, rather than finding nothing because there was nothing scannable — see the next step for how to tell these apart).

### Step 3.2: Distinguish "No PII Found" From "Nothing Scannable"

```bash
cat /tmp/scan-response-clean.json | python3 -c "
import json, sys
r = json.load(sys.stdin)
print('files_scanned:', r.get('files_scanned'))
print('files_skipped_unscannable:', r.get('files_skipped_unscannable'))
print('files_with_pii:', r.get('files_with_pii'))
"
```

**What to check**: per the FAQ in [Content Classification Scanner](content-classification-scanner.md#faq), if `files_skipped_unscannable` accounts for most of the volume's files, the scan did not actually inspect most content (likely Office/PDF files outside the scannable extension list — see [Remaining Limitations](content-classification-scanner.md#remaining-limitations) item 1) rather than confirming it's PII-free.

---

## Cleanup

```bash
# Delete the synthetic test file from the access point
aws s3api delete-object --bucket "$ACCESS_POINT_ARN" --key validation/pii-test-sample.txt

# Remove local temp files
rm -f /tmp/pii-test-sample.txt /tmp/scan-response.json /tmp/scan-response-clean.json

# Delete the CloudFormation stack (optional)
aws cloudformation delete-stack --stack-name fsxn-content-classification
```

> **Note**: Deleting the stack removes the scanner Lambda and the `ClassificationReportTable` (and any VPC Endpoints created in Deploy Mode 2). It does not touch the S3 Access Point or the underlying FSx for ONTAP volume — this scanner never creates or manages access points (see [Prerequisites](content-classification-scanner.md#an-existing-s3-access-point)).

---

## Timing Reference

| Phase | Duration | Notes |
|-------|----------|-------|
| Phase 1 (Deploy) | ~5 min | CloudFormation deploy |
| Phase 2 (PII discovery) | ~3 min | Upload + invoke + confirm ledger + confirm notification |
| Phase 3 (No-PII / troubleshooting paths) | ~2 min | Second invocation + response inspection |
| **Total** | **~10 min** | Full demo with all phases |

---

## Related Documents

- [Content Classification Scanner](content-classification-scanner.md)
- [Cyber Resilience Capability Map](cyber-resilience-capability-map.md#identify-id)
- [Data Classification Guide](data-classification.md)
- [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) — for chaining this scanner after a FlexClone-backed access point instead of using Deploy Mode 1
