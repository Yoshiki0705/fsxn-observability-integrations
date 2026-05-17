# AGENTS.md — FSx for ONTAP Observability Integrations

## Project Overview

Serverless observability integrations shipping Amazon FSx for NetApp ONTAP audit logs to multiple vendors via S3 Access Points. CloudFormation (YAML) + Python 3.12 Lambda + TypeScript tooling. Multi-vendor pattern library with bilingual (ja/en) documentation.

## Key Commands

```bash
# Install dependencies
npm install

# TypeScript typecheck
npx tsc --noEmit

# Lint
npm run lint

# Run all TypeScript tests
npm test

# Run Python tests for a specific vendor
cd integrations/datadog && python -m pytest tests/ -v

# Validate CloudFormation templates
pip install cfn-lint
cfn-lint integrations/*/template.yaml
cfn-lint shared/templates/*.yaml

# Deploy a vendor integration
bash shared/scripts/deploy.sh <vendor> <stack-name> --region ap-northeast-1

# Run full test suite
bash shared/scripts/test.sh
```

## Project Structure

```
integrations/<vendor>/       # Vendor-specific implementations
  ├── template.yaml          # CloudFormation (single self-contained stack)
  ├── lambda/handler.py      # Python 3.12 Lambda function
  ├── docs/{ja,en}/          # Bilingual setup guides
  └── tests/                 # pytest unit tests

shared/
  ├── lambda-layers/         # Reusable Lambda Layers (log-parser, s3ap-reader)
  ├── templates/             # Base CloudFormation templates (IAM, VPC, S3 AP)
  └── scripts/               # deploy.sh, test.sh

.kiro/steering/              # Kiro IDE steering files (do NOT modify without asking)
```

## Code Style

### Python (Lambda functions)

```python
"""Module docstring: one-line summary.

Extended description if needed.
"""

import json
import logging
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_BATCH_SIZE_BYTES = 5 * 1024 * 1024  # Constants: UPPER_SNAKE_CASE


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point. Type hints required. Google-style docstrings."""
    ...
```

- Python 3.12, PEP 8, type hints mandatory
- Use `urllib3` for HTTP (included in Lambda runtime), not `requests`
- Secrets from Secrets Manager, never environment variables for sensitive values
- Exponential backoff for all vendor API calls (max 3 retries)
- Batch processing respecting vendor size limits

### TypeScript

- Strict mode, named exports only
- ESLint + Prettier formatting
- `@aws-sdk/client-*` v3 (modular SDK)

### CloudFormation (YAML)

- 2-space indent
- PascalCase resource logical IDs: `LambdaExecutionRole`, `DeadLetterQueue`
- Stack name pattern: `fsxn-<vendor>-integration`
- Always include: IAM least-privilege, DLQ, CloudWatch Alarms

## Non-Obvious Patterns

### ⚠️ CRITICAL: FSx ONTAP S3 Access Points — Network Constraints

**FSx ONTAP S3 Access Points are NOT accessible via S3 Gateway VPC Endpoint.**

This is the #1 source of deployment failures. FSx ONTAP S3 APs route through the FSx data plane, not the standard S3 data plane.

| Lambda Placement | S3 AP Access | ONTAP REST API Access | Recommendation |
|-----------------|-------------|----------------------|----------------|
| **VPC 外 (no VPC config)** | ✅ Works | ❌ Requires VPC | Simplest for S3 AP only |
| **VPC 内 + S3 Gateway EP** | ❌ TIMEOUT | ✅ Works | Do NOT use for S3 AP |
| **VPC 内 + NAT Gateway** | ✅ Works | ✅ Works | Production recommended |
| **VPC 内 + Interface EP** | ❌ TIMEOUT | ✅ Works | Do NOT use for S3 AP |

**Root cause**: S3 Gateway VPC Endpoints only route traffic for the standard S3 service (`com.amazonaws.<region>.s3`). FSx ONTAP S3 Access Points use a different data path through the FSx service. Traffic to FSx S3 APs from within a VPC requires NAT Gateway or internet access.

**Design pattern for this project**:
- Lambda functions that ONLY read from S3 AP → Deploy **outside VPC** (simplest, lowest cost)
- Lambda functions that need BOTH S3 AP + ONTAP REST API → Deploy **in VPC with NAT Gateway**
- Lambda functions that ONLY call ONTAP REST API → Deploy **in VPC** (no NAT needed if using Interface VPC Endpoints for FSx)

### S3 Access Points for FSx ONTAP — ARN and IAM

FSx ONTAP S3 Access Points provide dual-protocol (NFS/SMB + S3) access to the same data without copying.

**Correct ARN format**:
```
arn:aws:s3:{region}:{account-id}:accesspoint/{access-point-name}
```

**IAM policy resource format**:
```yaml
# For GetObject/PutObject on objects:
Resource: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap/object/*

# For ListBucket on the access point itself:
Resource: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap
```

**boto3 usage** — Use the AP ARN as the `Bucket` parameter:
```python
s3_client.get_object(
    Bucket="arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
    Key="audit/svm-prod-01/2026/01/15/audit.json"
)
```

**S3 AP Resource Policy**: In addition to IAM, the S3 Access Point itself must have a resource policy granting access to the Lambda execution role. Use `s3control put-access-point-policy`.

### FSx ONTAP S3 AP — Unsupported S3 Features

The following S3 features are NOT supported on FSx ONTAP S3 Access Points:

| Feature | Status | Workaround |
|---------|--------|-----------|
| S3 Event Notifications / EventBridge | ❌ Not supported | Use polling (EventBridge Scheduler) or audit log bucket events |
| GetBucketNotificationConfiguration | ❌ Not supported | N/A — this is why we use a separate S3 bucket for audit logs |
| Object Lifecycle policies | ❌ Not supported | Implement custom cleanup Lambda |
| Object Versioning | ❌ Not supported | Use DynamoDB for version tracking |
| Presigned URLs | ❌ Not supported | Copy to standard S3 + presign |
| SSE-KMS (custom keys) | ❌ SSE-FSX only | Use FSx volume-level KMS encryption |
| PutObject > 5GB | ❌ 5GB limit | Multipart upload within 5GB |

**Key implication for this project**: We use a **standard S3 bucket** as the audit log destination (which supports EventBridge notifications), NOT the FSx ONTAP S3 Access Point directly. The S3 AP is used for Lambda to read the logs from the bucket.

Reference: [AWS Docs — S3 AP API Support](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html) | [AWS Blog — S3 Access Points for FSx](https://aws.amazon.com/blogs/storage/bridge-legacy-and-modern-applications-with-amazon-s3-access-points-for-amazon-fsx/)

### Audit log formats

FSx ONTAP outputs audit logs in EVTX (Windows Event Log binary) or XML format depending on SVM audit configuration (`vserver audit create -format {evtx|xml}`). The `shared/lambda-layers/log-parser/` handles both. EVTX files start with magic bytes `ElfFile\x00`. XML logs contain `<Event>` elements with system and event data.

Reference: [AWS Docs — File access auditing](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)

### Vendor API key caching in Lambda

API keys are fetched from Secrets Manager once per Lambda execution context (cold start) and cached in a module-level variable. This avoids per-invocation Secrets Manager calls. The `_api_key_cache` pattern is intentional — do not refactor into per-request fetching.

### Bilingual documentation sync

Japanese (`docs/ja/`) is the primary language. English (`docs/en/`) must mirror the same heading structure and content. When modifying docs, always update both languages. Code examples are identical across languages.

## Vendor API Reference (Quick Lookup)

| Vendor | Endpoint | Auth Header | Max Batch | Firehose |
|--------|----------|-------------|-----------|----------|
| Datadog | `https://http-intake.logs.{site}/api/v2/logs` | `DD-API-KEY: <key>` | 5MB / 1000 items | ✅ |
| New Relic | `https://log-api.newrelic.com/log/v1` (US) | `Api-Key: <license>` | 1MB | ✅ |
| Grafana/Loki | `https://<instance>.grafana.net/loki/api/v1/push` | Basic Auth (ID + token) | ~4MB recommended | ❌ |
| Splunk | `https://<host>:8088/services/collector/event` | `Authorization: Splunk <token>` | No hard limit | ✅ (built-in) |
| Elastic | `https://<cluster>/_bulk` | `Authorization: ApiKey <key>` | ~10MB recommended | ❌ |
| Dynatrace | `https://<env>.live.dynatrace.com/api/v2/logs/ingest` | `Authorization: Api-Token <token>` | 1MB | ✅ |
| Sumo Logic | `https://endpoint<N>.collection.sumologic.com/...` | Embedded in URL | 1MB | ❌ |
| Honeycomb | `https://api.honeycomb.io/1/batch/<dataset>` | `X-Honeycomb-Team: <key>` | 5MB | ❌ |
| OTel (OTLP) | `http://<collector>:4318/v1/logs` | Configurable | Configurable | ❌ |

Sources: [Datadog Logs API](https://docs.datadoghq.com/api/latest/logs/) | [New Relic Log API](https://docs.newrelic.com/docs/enable-new-relic-logs-http-input/) | [Grafana Loki HTTP API](https://grafana.com/docs/loki/latest/reference/loki-http-api/) | [Splunk HEC](https://docs.splunk.com/Documentation/Splunk/9.4.0/Data/FormateventsforHTTPEventCollector) | [OpenTelemetry Lambda](https://github.com/open-telemetry/opentelemetry-lambda)

## AWS Service Patterns

### EventBridge Scheduler for audit log processing

FSx for ONTAP S3 Access Points do not support S3 Event Notifications or EventBridge object-level events. Use EventBridge Scheduler to invoke the audit log processor Lambda on a periodic schedule (e.g., every 5 minutes). Lambda uses checkpointing (DynamoDB or S3 marker objects) to track which audit log files have been processed and only reads newly rotated files.

### Lambda Powertools (recommended for new integrations)

[Powertools for AWS Lambda (Python)](https://aws.amazon.com/powertools-for-aws-lambda/) provides structured logging, tracing, and metrics out of the box. Consider adopting for new vendor integrations to standardize observability of the Lambda functions themselves.

### Kinesis Data Firehose alternative path

For high-volume logs (>1000 events/second sustained), prefer the Firehose path over direct Lambda-to-vendor delivery. Firehose provides automatic buffering, retry, and backpressure handling. Splunk and Datadog have built-in Firehose destinations.

## Testing Rules

- Write pytest unit tests for all Lambda handler logic
- Mock all AWS service calls (boto3) and HTTP calls (urllib3)
- Use `conftest.py` for shared fixtures (env vars, sample events)
- Sample event data lives in `tests/test_data/`
- Tests must be deterministic — no real API calls, no network dependencies
- Run `python -m pytest tests/ -v` before marking any task complete

## Boundaries

### ✅ Allowed without asking
- Read any file in the repository
- Run lint, typecheck, tests
- Create/modify files within `integrations/<vendor>/`
- Create/modify files within `docs/`

### ⚠️ Ask first
- Modify `shared/` (affects all integrations)
- Add or remove npm/pip dependencies
- Change `.kiro/steering/` files
- Modify `.github/workflows/`

### 🚫 Never
- Commit secrets, API keys, `.env` files, or PEM keys
- Force push to main
- Modify `.git/` directory
- Delete `shared/lambda-layers/` or `shared/templates/`
- Use `requests` library in Lambda (not in runtime, use `urllib3`)
- Store secrets in Lambda environment variables (use Secrets Manager ARN only)

## Key Files

- `integrations/datadog/lambda/handler.py` — Reference implementation (fully working)
- `integrations/datadog/template.yaml` — Reference CloudFormation template
- `shared/lambda-layers/log-parser/python/fsxn_log_parser/parser.py` — EVTX/XML parser
- `shared/lambda-layers/s3ap-reader/python/s3ap_reader/reader.py` — S3 AP utility
- `shared/templates/iam-base-roles.yaml` — IAM role pattern
- `.kiro/steering/vendor-integration.md` — New vendor checklist

## Deploying Prerequisites

Before any vendor integration, deploy the prerequisites stack:

```bash
# 1. Deploy S3 bucket + Access Point + EventBridge
aws cloudformation deploy \
  --template-file shared/templates/prerequisites.yaml \
  --stack-name fsxn-observability-prerequisites \
  --parameter-overrides AuditLogBucketName=<unique-name> \
  --capabilities CAPABILITY_IAM

# 2. Enable FSx ONTAP audit logging
bash shared/scripts/ontap-audit-setup.sh --endpoint <ip> --svm <name> --dry-run

# 3. Deploy vendor stack using outputs from step 1
```

### EMS/FPolicy Stacks (CAPABILITY_NAMED_IAM Required)

The EMS Webhook and FPolicy templates create named IAM roles, so they require `CAPABILITY_NAMED_IAM`:

```bash
# EMS Webhook stack
aws cloudformation deploy \
  --template-file shared/templates/ems-webhook-apigw.yaml \
  --stack-name fsxn-ems-webhook \
  --parameter-overrides LambdaFunctionArn=<ARN> \
  --capabilities CAPABILITY_NAMED_IAM

# FPolicy stack (ECS Fargate + SQS + EventBridge)
aws cloudformation deploy \
  --template-file shared/templates/fpolicy-apigw.yaml \
  --stack-name fsxn-fp-srv \
  --parameter-overrides \
    ComputeType=fargate \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    FsxnSvmSecurityGroupId=<sg-id> \
    ContainerImage=<ecr-uri>:v2-timeout-fix \
  --capabilities CAPABILITY_NAMED_IAM
```

**Architecture:**
- EMS: ONTAP EMS → Webhook (HTTPS) → API Gateway → Lambda → Vendor
- FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → EventBridge → Lambda → Vendor
- FPolicy uses a proprietary binary protocol over TCP (NOT HTTP/HTTPS)
- ONTAP connects directly to Fargate task IP (NLB is health-check only)

Two patterns exist:
- **Pattern A (existing FSx ONTAP)**: Deploy prerequisites.yaml → enable audit → deploy vendor stack
- **Pattern B (from scratch)**: Create FSx ONTAP → then Pattern A

Full guide: `docs/ja/prerequisites.md` / `docs/en/prerequisites.md`

## Adding a New Vendor Integration

1. Create directory: `mkdir -p integrations/<vendor>/{lambda,docs/{ja,en},tests}`
2. Copy reference: use `integrations/datadog/` as the template
3. Implement `lambda/handler.py` with vendor-specific API formatting
4. Create `template.yaml` following the CloudFormation structure in steering
5. Write bilingual docs: `docs/ja/setup-guide.md` and `docs/en/setup-guide.md`
6. Add pytest tests with mocked API responses
7. Update root `README.md` vendor table (change 🚧 to ✅)
8. Update `docs/{ja,en}/vendor-comparison.md`

## Commit Convention

```
feat: add New Relic integration
fix: handle empty EVTX files in log parser
docs: update Datadog setup guide for AP1 region
test: add batch splitting edge case tests
chore: update cfn-lint to v1.x
```

Conventional Commits format. English only. Keep subject under 72 characters.
