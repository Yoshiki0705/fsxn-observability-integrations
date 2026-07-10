# Content-Level PII Classification Scanner — Closing the CSF 2.0 Identify Gap

🌐 [日本語](../ja/content-classification-scanner.md) | **English** (this page)

## Executive Summary

The [DII Capability Map](dii-capability-map.md) is direct about a gap in the Identify function: this repository's [Data Classification Guide](data-classification.md) defines a schema-level classification (which *fields* — `UserName`, `ObjectName` — are PII), but does not scan file *contents* the way NetApp's data classification tooling does for the CSF 2.0 Identify function.

This guide implements that content-level scan using Amazon Comprehend's managed PII entity detection, exposed as a standalone Lambda function that reads files through an existing S3 Access Point:

1. **List objects** through a given S3 Access Point (`ListObjectsV2`) and filter to scannable text/structured-data extensions (`.txt`, `.csv`, `.json`, `.log`, and others — binary formats like Office documents are out of scope; see [Remaining Limitations](#remaining-limitations) below).
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

> **Diagram description (text alternative)**: A single Lambda (`ScannerFunction`) takes an S3 Access Point ARN as input — either standalone or from the Verified-Clean Recovery Point Guide's `AttachAccessPoint` step. It lists objects via `ListObjectsV2`, filters to scannable extensions with non-zero size, reads each file (fully or Range-sampled if oversized), splits the content into under-100KB UTF-8 chunks, calls Comprehend `DetectPiiEntities` per chunk, and aggregates results by entity type with count and max confidence. The aggregated report is written to DynamoDB, and an SNS notification fires if PII was found. The diagram above is ASCII art; this paragraph is the complete textual equivalent for screen-reader users.

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

> **Data Protection Officer/Privacy Engineer lens**: The report records `highest_confidence_by_type` per entity, but the scanner does **not** filter or flag low-confidence matches — a single `EMAIL` detection at Comprehend confidence 0.31 counts toward `files_with_pii` exactly the same as one at 0.99. Before using `files_with_pii`/`pii_density_by_type` as an input to a regulatory PII inventory or a DPIA, review the per-entity `highest_confidence_by_type` in the raw findings (not just the summary counts) and apply your own confidence floor — treating every low-confidence match as confirmed PII risks overstating exposure; treating every match as noise risks understating it. Neither judgment call is one this scanner makes for you.

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

> **Legal/eDiscovery & Litigation Hold Specialist lens**: This lens differs from the Data Protection Officer/Privacy Engineer lens elsewhere in this guide — that lens covers regulatory PII inventory judgment calls; this one covers what happens if the *scan itself* becomes relevant to litigation. Two considerations: (1) if a legal hold is in effect on a volume, running this scanner against it does not itself violate the hold (it's read-only and non-destructive — see Security Considerations), but the resulting DynamoDB report and its file-path findings may themselves become discoverable material, since they document what sensitive content existed and where at scan time; preserve scan reports under the same hold if the underlying data is subject to one. (2) The scanner never captures matched PII values (see Entity Aggregation above), so it cannot serve as a substitute for a legal team's own document review when specific PII values (not just entity types) need to be produced or redacted for a matter — route that to your standard eDiscovery tooling instead.

---

## Remaining Limitations

Being direct about what this scanner does **not** do:

1. **No document-format parsing.** Office documents (`.docx`, `.xlsx`, `.pdf`) are not text-extracted — this scanner only reads raw bytes and UTF-8-decodes them, which works for plain text/structured formats but produces garbage (and no useful findings) for binary Office/PDF formats. Extending this would require a document-parsing library (e.g., via a Lambda Layer) not currently included.
2. **English-centric extension list, but multi-language content detection.** The `SCANNABLE_EXTENSIONS` filter is format-based, not language-based — Comprehend itself supports 12 languages via `language_code`, but this scanner processes one language per invocation. Mixed-language volumes need either multiple runs with different `language_code` values or a language-detection pre-step (not implemented).
3. **Sampling, not full-file scanning, above 5 MB.** Large log or CSV files are only scanned in their first 500 KB by default — PII appearing later in a large file is not detected. Increase `DEFAULT_MAX_FILE_BYTES`/`sample_bytes` if this matters for your data, at increased Comprehend cost.
4. **Cost scales with file count and size.** Comprehend `DetectPiiEntities` is priced per unit of text processed. Scanning a large volume with many/large scannable files can generate meaningful Comprehend charges — the `max_files` cap exists specifically to bound this per invocation.
5. **No automatic re-scan on file change.** This is an on-demand/scheduled scanner, not an event-driven one. Pair it with your own EventBridge Scheduler rule (following the pattern in the [Automated Response Guide](automated-response-guide.md#deployment)'s TTL cleanup schedule) if you want periodic re-classification.
6. **A Lambda timeout mid-scan loses the entire run's findings, not just the unscanned files.** The scanner writes its DynamoDB report once, after the full `ListObjectsV2`/classify loop completes — there is no partial-progress checkpoint. If `LambdaTimeoutSeconds` is exceeded partway through a large volume, Lambda kills the invocation before the `put_item` call, and no report (not even a partial one) is written for that run. Size `LambdaTimeoutSeconds` and `max_files` conservatively for your expected file count and average file size, and check CloudWatch Logs (not just the DynamoDB table) to distinguish "scan found nothing" from "scan never completed."

> **Recovery Test Engineer lens**: If chaining this scanner after the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s workflow, sequencing matters — that workflow's `Cleanup` step always detaches the S3 Access Point and deletes the FlexClone, on both the success and failure paths (see that guide's Architecture). Invoke this scanner's classification *before* that workflow reaches `Cleanup`, either as an additional Step Functions state inserted ahead of it or as a synchronous follow-up call using the same execution's `access_point_arn` output — invoking it after the workflow has already completed will fail because the access point no longer exists.

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

> **Network origin determines whether you need `VpcId`**: a [VPC-scoped access point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-vpc.html) — which is what `AttachAccessPoint` creates — has no route from outside the VPC it's bound to; a Lambda outside that VPC cannot reach it at all, regardless of IAM permissions. An internet-origin access point (any access point without a `VpcConfiguration`) is reachable without a VPC. See [Deployment](#deployment) below for the `VpcId` parameter that governs which mode this stack deploys in.

---

## Deployment

### Deploy Mode 1: Standalone (Internet-Origin Access Point)

Use this when scanning an access point that does **not** have a `VpcConfiguration` — the simpler, cheaper mode, since no VPC Endpoints are created:

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

### Deploy Mode 2: In-VPC (VPC-Scoped Access Point)

Use this when scanning a VPC-scoped access point — required if chaining after the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s `AttachAccessPoint` step, since that step always creates a VPC-scoped access point:

```bash
aws cloudformation deploy \
  --template-file shared/templates/content-classification-scanner.yaml \
  --stack-name fsxn-content-classification \
  --parameter-overrides \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    RouteTableIds=<route-table-1>,<route-table-2> \
    DefaultLanguageCode=en \
    DefaultMaxFiles=500 \
    NotificationTopicArn=<optional-sns-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

Setting `VpcId` changes both the scanner Lambda (adds `VpcConfig`) and the stack's resources (adds S3/DynamoDB Gateway Endpoints and Comprehend/SNS Interface Endpoints, unless `CreateVpcEndpoints=false` because your VPC already has them — e.g., reusing `restore-verification.yaml`'s VPC only covers Secrets Manager/STS/FSx from that stack, not these four).

### What the Stack Creates

- One Lambda function (`{stack-name}-scanner`) — with or without `VpcConfig` depending on `VpcId`
- DynamoDB report table (`{stack-name}-reports`)
- CloudWatch Logs (365-day retention — reports double as compliance evidence)
- If `VpcId` is set and `CreateVpcEndpoints=true` (default): S3 Gateway Endpoint, DynamoDB Gateway Endpoint, Comprehend Interface Endpoint, SNS Interface Endpoint

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

> **This chaining pattern requires Deploy Mode 2 (In-VPC)**: `AttachAccessPoint` always creates a VPC-scoped access point, and this scanner must run inside that same VPC to reach it — see the network-origin note in [Prerequisites](#an-existing-s3-access-point) above. Deploying this stack in standalone mode (no `VpcId`) against a chained FlexClone access point will fail at the `ListObjectsV2` call every time, since there is no network route to try intermittently.

---

## Configuration Reference

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `DefaultLanguageCode` | en | Amazon Comprehend language code for `DetectPiiEntities` (12 supported languages) |
| `DefaultMaxFiles` | 500 | Cap on files scanned per invocation (cost/runtime control); overridable per-invocation via the `max_files` payload key |
| `LambdaMemorySize` | 512 MB | Scanner Lambda memory |
| `LambdaTimeoutSeconds` | 600 | Scanner Lambda timeout — size to your expected file count |

> **FinOps/Cost Optimization Engineer lens**: [Amazon Comprehend's synchronous PII detection pricing](https://aws.amazon.com/comprehend/pricing/) is metered per 100-character unit processed, with a per-request minimum — cost here scales with total scanned *content volume*, not file count, so a handful of very large text files can cost more than thousands of small ones. Lambda invocation cost and DynamoDB `PutItem` cost are comparatively negligible next to Comprehend charges for any non-trivial scan. Before running this against a large volume, estimate cost from a representative sample (scan one department's share with `max_files` capped low, note the aggregate size scanned, then extrapolate) rather than assuming a fixed per-file cost — see [Remaining Limitations](#remaining-limitations) item 4 and the FAQ for related guidance on bounding a single run's cost.

---

## Security Considerations

- **Data minimization by design**: findings never contain the matched PII text — only entity type, count, and confidence score. See [Entity Aggregation](#entity-aggregation--data-minimization-by-design) above.
- **No write access to scanned volumes**: the scanner only calls `s3:GetObject`/`s3:ListBucket` — it cannot modify, redact, or delete the files it scans.
- **Report table access should be restricted**: while the report itself doesn't contain PII values, it does contain *where* PII-shaped data was found (file paths) and *how much* — apply the same access restrictions you'd apply to any inventory of sensitive-data locations.
- **Comprehend is a regional, AWS-managed service**: text sent to `DetectPiiEntities` is processed within the AWS Region you invoke it in; see [Amazon Comprehend's data privacy documentation](https://docs.aws.amazon.com/comprehend/latest/dg/data-privacy.html) for the service's own data handling commitments.
- **VPC-scoped access points have no route from outside their bound VPC**: this is a network property of the access point itself (see [AWS's network-origin comparison](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)), not something IAM alone can work around. When scanning a VPC-scoped access point, deploy this stack with `VpcId` set (Deploy Mode 2) so the scanner Lambda runs inside that VPC with a route to S3 via the Gateway Endpoint this stack creates.

> **Procurement/Third-Party Risk Management (TPRM) Analyst lens**: For vendor-assessment questionnaires that ask "is data sent to a third party" or "where is data processed" — this pipeline sends file content to Amazon Comprehend, a first-party AWS managed service, not an external third-party vendor; processing stays within the AWS Region you deploy to (see the data-privacy point above). Data retention: this scanner does not delete anything on its own — the DynamoDB report table has no TTL configured by default, so classification reports persist indefinitely until you delete the stack or add your own TTL attribute; factor that into your organization's data-retention schedule if reports are subject to one, since the reports themselves contain file paths (Sensitive per the Data Classification Guide) even though they exclude raw PII values.

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

> **QA/Test Automation Engineer lens**: All 23 tests mock the `s3` and `comprehend` boto3 clients directly — no test calls a real S3 Access Point or Amazon Comprehend endpoint. This makes the suite fast and independent of AWS credentials, but it also means the tests validate this module's *own* logic (chunking, aggregation, error handling) correctly, not whether the mocked Comprehend response shape still matches the real `DetectPiiEntities` API. Re-run a manual smoke test against a real (non-production) access point and Comprehend endpoint after any `boto3`/`botocore` version bump, and don't treat `pytest` passing as proof the Lambda will behave identically in a live AWS account.

> **Observability Engineer lens**: The stack ships CloudWatch Logs only — no CloudWatch Alarm on Lambda errors, throttles, or timeouts. Given the "timeout loses the whole run" behavior noted in [Remaining Limitations](#remaining-limitations) item 6, add your own alarm on this Lambda's `Errors`/`Duration` metrics (or route failures through the SNS topic already wired for PII-found notifications) so a silently-timed-out scan doesn't read as "no PII found" by omission.

> **On-Call Engineer (SRE) lens**: This scanner is not a paging-worthy service by design — it's an on-demand/scheduled batch job (see [Remaining Limitations](#remaining-limitations) item 5), not a request-serving pipeline with an SLO. If you do get paged because a scheduled invocation failed: check CloudWatch Logs for the invocation first (see the FAQ's "zero findings" question for why the DynamoDB table alone can be misleading), then re-invoke manually with the same `access_point_arn` once the underlying cause (timeout, throttling, or a stale/deleted access point if chained after `restore-verification.yaml`) is addressed. There is no ledger row to clean up and no orphaned resource to worry about on failure — this scanner never creates infrastructure, only reads from an access point someone else manages.

---

## Related Documents

- [DII Capability Map](dii-capability-map.md) — the Identify-function Remaining Gap this scanner implements a fix for
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

**Q: I deployed standalone (no `VpcId`) and every invocation fails at `ListObjectsV2` — why?**
A: The `access_point_arn` you're passing is almost certainly VPC-scoped (most commonly, one produced by the [Verified-Clean Recovery Point Guide](verified-recovery-point-guide.md)'s `AttachAccessPoint` step). A VPC-scoped access point has no network route from outside its bound VPC — this fails deterministically, not intermittently, regardless of IAM permissions. Redeploy with `VpcId`/`SubnetIds`/`SecurityGroupId`/`RouteTableIds` set (Deploy Mode 2) so the scanner runs inside the same VPC the access point is bound to.

**Q: Does a low `Score` (confidence) on a PII entity mean I can ignore it?**
A: Not automatically — this scanner doesn't apply a confidence floor for you (see the Data Protection Officer/Privacy Engineer lens note under [Entity Aggregation](#entity-aggregation--data-minimization-by-design)). It records the highest confidence seen per entity type per file so *you* can apply a threshold appropriate to your regulatory context; it does not decide for you what confidence level constitutes "found" PII.

**Q: My scan of a large volume shows zero findings in DynamoDB — did it actually run?**
A: Check CloudWatch Logs for that invocation before concluding "no PII found." Because the report is written once at the end of the handler (see [Remaining Limitations](#remaining-limitations) item 6), a Lambda timeout partway through a large scan produces the same DynamoDB-side symptom (no report row) as a scan that genuinely found nothing — the two are only distinguishable via the Lambda's own logs/duration metrics.
