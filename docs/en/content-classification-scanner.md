# Content-Level PII Classification Scanner — Closing the CSF 2.0 Identify Gap

🌐 [日本語](../ja/content-classification-scanner.md) | **English** (this page)

## Executive Summary

The [DII Capability Map](dii-capability-map.md) is direct about a gap in the Identify function: this repository's [Data Classification Guide](data-classification.md) defines a schema-level classification (which *fields* — `UserName`, `ObjectName` — are PII), but does not scan file *contents* the way NetApp's data classification tooling does for the CSF 2.0 Identify function.

This guide implements that content-level scan using Amazon Comprehend's managed PII entity detection, exposed as a standalone Lambda function that reads files through an existing S3 Access Point:

1. **List objects** through a given S3 Access Point (`ListObjectsV2`) and filter to scannable text/structured-data extensions (`.txt`, `.csv`, `.json`, `.log`, and others — binary formats like Office documents are out of scope; see [Genuine Limitations](#genuine-limitations) below).
2. **Read and chunk** each file's content into byte-bounded segments under Amazon Comprehend's per-call size ceiling.
3. **Call `DetectPiiEntities`** per chunk and aggregate entity type, count, and confidence score per file — **the PII values themselves are never persisted**, only entity type/offset/confidence.
4. **Write a classification report** to DynamoDB and optionally notify via SNS when PII is found.

> **Scope note**: This is a PII *discovery* tool, not a redaction, remediation, or general-purpose malware/content scanner. It answers "does this volume contain content that looks like PII, and roughly how much" — the CSF 2.0 Identify-function question of asset/data understanding, not Protect, Detect, or Respond.

**Key capabilities:**
- Amazon Comprehend `DetectPiiEntities` — managed PII detection across [12 languages](https://docs.aws.amazon.com/comprehend/latest/dg/supported-languages.html), dozens of entity types (SSN, credit card numbers, bank accounts, national ID numbers, and more)
- Data-minimizing by design: findings record entity type + confidence, never the matched text itself
- Works against any existing FSx for ONTAP S3 Access Point — standalone, or chained after the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s FlexClone-backed access point for zero production impact
- Oversized files are sampled (first N bytes), not skipped entirely, so large log/CSV files still contribute a partial signal
- DynamoDB report ledger, doubling as CSF 2.0 Identify-function evidence for audits

**When to run this:**
- Periodically against volumes containing user-generated content (shares, home directories, exports) to maintain an up-to-date picture of where PII actually lives
- Against a [FlexClone verification access point](verified-recovery-point-guide.md) immediately after ransomware verification, combining both scans against the same isolated clone
- Before onboarding a volume to a new observability/SIEM destination, to confirm what a forensics dashboard or exported log sample might expose

---

## Architecture

```
+-------------------------------------------------------------------+
| Input: any existing S3 Access Point ARN                           |
| (standalone, or from verified-recovery-point-guide.md's            |
|  AttachAccessPoint step)                                          |
+-------------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------------+
| Lambda: ScannerFunction                                            |
|                                                                    |
|  ListObjectsV2 (via access point)                                  |
|       |                                                            |
|       +-> filter: scannable extension? size > 0?                  |
|              |                                                     |
|              v                                                     |
|         GetObject (full or Range-sampled if oversized)             |
|              |                                                     |
|              v                                                     |
|         chunk into <100KB UTF-8 segments                           |
|              |                                                     |
|              v                                                     |
|         Comprehend DetectPiiEntities (per chunk)                   |
|              |                                                     |
|              v                                                     |
|         aggregate entity_type -> count, max confidence             |
+-------------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------------+
| DynamoDB: classification report (per access point, per run)        |
| SNS: optional notification if PII found                            |
+-------------------------------------------------------------------+
```

---

## How Classification Works

### File Selection

Only files with a scannable extension are read — this scanner does not implement document-format parsing (no Office/PDF text extraction):

```
.txt  .csv  .tsv  .json  .xml  .log  .md  .yaml  .yml  .ini  .conf  .sql  .html  .htm
```

Zero-byte files are skipped. Files above `DEFAULT_MAX_FILE_BYTES` (5 MB) are **sampled**, not skipped — only the first 500 KB is read via an S3 Range `GetObject`, and the finding records `sampled: true` so you know the result is partial.

### Chunking for Comprehend's Size Limit

[`DetectPiiEntities`](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html) enforces a 100 KB UTF-8 byte-size ceiling per call. The scanner splits file content into chunks under that limit, breaking on line boundaries where possible so an entity (e.g., an email address) is not split across a chunk boundary unnecessarily:

```python
# Simplified — see content_classifier.py's _chunk_text for the full
# line-boundary-aware implementation
for chunk in _chunk_text(file_text, target_bytes=98_000):
    entities = comprehend.detect_pii_entities(Text=chunk, LanguageCode="en")
```

### Entity Aggregation — Data Minimization by Design

For each file, findings record **only**:
- Entity `Type` (e.g., `EMAIL`, `SSN`, `CREDIT_DEBIT_NUMBER`, `BANK_ACCOUNT_NUMBER` — [full type list](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html))
- Count of occurrences per type
- Highest confidence `Score` observed per type

The matched text itself (the actual email address, SSN, etc.) is **never written to the report, logs, or DynamoDB**. This mirrors the [Data Classification Guide](data-classification.md)'s pseudonymization guidance — a report saying "this file contains 3 SSN-pattern matches at 0.97+ confidence" is useful for prioritizing remediation without itself becoming a new PII exposure surface.

### Error Handling — One Bad File Doesn't Abort the Scan

Read failures (`AccessDenied`, `NoSuchKey`), decode failures, and Comprehend API errors (`TextSizeLimitExceededException`, throttling) are captured per-file in the `error` field rather than raised — a single problematic file is recorded and skipped, and the scan continues across the rest of the volume.

---

## Comparison: Schema-Level vs Content-Level Classification

| Aspect | Schema-Level (Data Classification Guide) | Content-Level (this scanner) |
|--------|---------------------------------------------|-------------------------------|
| What it classifies | Which *fields* in audit/FPolicy events are PII (`UserName`, `ObjectName`) | Which *file contents* on the volume contain PII-shaped data |
| CSF 2.0 function | Identify (metadata-level asset understanding) | Identify (data-level asset understanding) |
| Mechanism | Static field classification matrix (documentation) | Amazon Comprehend `DetectPiiEntities` (ML inference) |
| Coverage | Every event field this repo's pipelines emit | Text/structured-data files matching scannable extensions only |
| Automation in this repo | ✅ Full (reference table) | ✅ Full (this scanner) |

> **Compliance lens (HIPAA/FISC/SOC2)**: Combine both. The schema-level guide tells you which *pipeline fields* to restrict via vendor RBAC (dashboards showing `user`/`path` are displaying PII by definition). This scanner tells you which *volumes/files* likely contain PII in their content, informing where to apply DLP controls, access restrictions, or a formal data classification label at the storage layer. Neither replaces a manual review by your data protection officer for regulatory purposes — see the scope note in the Data Classification Guide.

---

## Genuine Limitations

Being direct about what this scanner does **not** do:

1. **No document-format parsing.** Office documents (`.docx`, `.xlsx`, `.pdf`) are not text-extracted — this scanner only reads raw bytes and UTF-8-decodes them, which works for plain text/structured formats but produces garbage (and no useful findings) for binary Office/PDF formats. Extending this would require a document-parsing library (e.g., via a Lambda Layer) not currently included.
2. **English-centric extension list, but multi-language content detection.** The `SCANNABLE_EXTENSIONS` filter is format-based, not language-based — Comprehend itself supports 12 languages via `language_code`, but this scanner processes one language per invocation. Mixed-language volumes need either multiple runs with different `language_code` values or a language-detection pre-step (not implemented).
3. **Sampling, not full-file scanning, above 5 MB.** Large log or CSV files are only scanned in their first 500 KB by default — PII appearing later in a large file is not detected. Increase `DEFAULT_MAX_FILE_BYTES`/`sample_bytes` if this matters for your data, at increased Comprehend cost.
4. **Cost scales with file count and size.** Comprehend `DetectPiiEntities` is priced per unit of text processed. Scanning a large volume with many/large scannable files can generate meaningful Comprehend charges — the `max_files` cap exists specifically to bound this per invocation.
5. **No automatic re-scan on file change.** This is an on-demand/scheduled scanner, not an event-driven one. Pair it with your own EventBridge Scheduler rule (following the pattern in the [Automated Response Guide](automated-response-guide.md#deployment)'s TTL cleanup schedule) if you want periodic re-classification.

---

## Prerequisites

### AWS Permissions

The Lambda execution role requires:

```
# S3 Access Point object read
- s3:ListBucket / s3:GetObject  (scoped to arn:aws:s3:*:*:accesspoint/*)

# Amazon Comprehend (no resource-level permissions supported — DetectPiiEntities
# is a stateless synchronous inference API with no addressable resource)
- comprehend:DetectPiiEntities

# Classification report ledger
- dynamodb:PutItem  (scoped to the report table)
```

### An Existing S3 Access Point

This scanner does **not** create or manage S3 Access Points — pass the ARN of one that already exists. Two common sources:
- An access point you manage directly against a production or DR volume
- The `access_point_arn` output from the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s `AttachAccessPoint` step, scanning the same FlexClone used for ransomware verification

---

## Deployment

### One Stack Deploy

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

The stack creates:
- One Lambda function (`{stack-name}-scanner`)
- DynamoDB report table (`{stack-name}-reports`)
- CloudWatch Logs (365-day retention — reports double as compliance evidence)

### Invoking the Scanner

```bash
aws lambda invoke \
  --function-name fsxn-content-classification-scanner \
  --payload '{
    "access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/verify-vol-data-20260710",
    "language_code": "en",
    "max_files": 500
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json
```

### Chaining After Recovery Verification

To scan the same isolated FlexClone used for ransomware verification (rather than production data), invoke this Lambda with the `access_point_arn` produced by the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s `AttachAccessPoint` Step Functions task — either by adding a state to that state machine, or as a separate follow-up invocation using the same execution's output.

---

## Configuration Reference

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `DefaultLanguageCode` | en | Amazon Comprehend language code for `DetectPiiEntities` (12 supported languages) |
| `DefaultMaxFiles` | 500 | Cap on files scanned per invocation (cost/runtime control); overridable per-invocation via the `max_files` payload key |
| `LambdaMemorySize` | 512 MB | Scanner Lambda memory |
| `LambdaTimeoutSeconds` | 600 | Scanner Lambda timeout — size to your expected file count |

---

## Security Considerations

- **Data minimization by design**: findings never contain the matched PII text — only entity type, count, and confidence score. See [Entity Aggregation](#entity-aggregation--data-minimization-by-design) above.
- **No write access to scanned volumes**: the scanner only calls `s3:GetObject`/`s3:ListBucket` — it cannot modify, redact, or delete the files it scans.
- **Report table access should be restricted**: while the report itself doesn't contain PII values, it does contain *where* PII-shaped data was found (file paths) and *how much* — apply the same access restrictions you'd apply to any inventory of sensitive-data locations.
- **Comprehend is a regional, AWS-managed service**: text sent to `DetectPiiEntities` is processed within the AWS Region you invoke it in; see [Amazon Comprehend's data privacy documentation](https://docs.aws.amazon.com/comprehend/latest/dg/data-privacy.html) for the service's own data handling commitments.

---

## Testing

The `content_classifier.py` module has 23 unit tests covering:

| Category | What's Verified |
|----------|-----------------|
| Text chunking | Empty input, single chunk, multi-chunk splitting, content-preserving reassembly, hard-split of an oversized single line, chunk target below Comprehend's limit |
| Per-file classification | No PII found, PII found with aggregated counts/confidence, multi-chunk aggregation, read failure handling, Comprehend failure handling, empty-file skip, oversized-file Range sampling, confidence rounding |
| Volume-level orchestration | Unsupported language rejection, unscannable-extension filtering, zero-byte skip, PII density aggregation, clean-file exclusion from findings, error-file inclusion in findings, `max_files` cap enforcement, report serialization capping, sampled-file tracking |

```bash
python3 -m pytest shared/python/tests/test_content_classifier.py -v
# 23 passed in 0.08s
```

---

## Related Documents

- [DII Capability Map](dii-capability-map.md) — the Identify-function Genuine Gap this scanner implements a fix for
- [Data Classification Guide](data-classification.md) — the schema-level (field-name) classification this scanner complements at the content level
- [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) — the FlexClone + S3 Access Point pattern this scanner can chain after, for zero-production-impact scanning
- [Automated Response Guide](automated-response-guide.md) — the containment-phase module whose protective snapshots are a natural scan target via the recovery verification workflow
- [Governance & Compliance](governance-and-compliance.md) — where classification reports fit as Identify-function evidence

## FAQ

**Q: Does this scanner redact or remove PII from files?**
A: No. This is a discovery-only tool, matching the CSF 2.0 Identify function's scope (inventory and understanding, not remediation). Redaction would require a separate write path this module deliberately does not implement.

**Q: Can I scan a production volume directly, not just a FlexClone?**
A: Yes — pass any S3 Access Point ARN, including one attached directly to a production volume. The FlexClone pattern in the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md) is recommended when you want zero read-load impact on production and want to combine the scan with ransomware verification, but it's not required.

**Q: Why does the scanner skip Office documents and PDFs?**
A: This module intentionally scopes to plain-text and structured-data formats to avoid depending on a document-parsing library. If your volumes are dominated by Office/PDF content, consider Amazon Textract or a document-extraction Lambda Layer as a pre-processing step feeding this scanner's `classify_object` logic with extracted text instead of raw bytes.

**Q: How do I avoid excessive Comprehend costs on a very large volume?**
A: Use `max_files` to cap the per-invocation scan size, and consider running the scanner against a representative subset (e.g., one department's share) rather than an entire multi-terabyte volume in one pass. Comprehend pricing is per-unit of text processed, so cost scales with total scanned content, not file count alone.
