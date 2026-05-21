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

## FPolicy Operations

```bash
# Build and push FPolicy server image (MUST use linux/amd64 for Fargate)
bash shared/fpolicy-server/build-and-push.sh v2-timeout-fix

# Start/stop FPolicy Fargate service
bash shared/scripts/fpolicy-fargate-control.sh start
bash shared/scripts/fpolicy-fargate-control.sh stop
bash shared/scripts/fpolicy-fargate-control.sh status

# Update ONTAP FPolicy External Engine IP after task restart
bash shared/scripts/fpolicy-update-engine-ip.sh --auto
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

**VPC-internal Lambda with only a Gateway Endpoint timed out accessing Internet-origin FSx ONTAP S3 Access Points in our environment.**

This is the #1 source of deployment failures. The observed behavior is that Internet-origin S3 APs require an internet-routed path (NAT Gateway or VPC-external Lambda) when accessed from within a VPC.

| Lambda Placement | S3 AP Access | ONTAP REST API Access | Recommendation |
|-----------------|-------------|----------------------|----------------|
| **VPC 外 (no VPC config)** | ✅ Works | ❌ Requires VPC | Simplest for S3 AP only |
| **VPC 内 + S3 Gateway EP only** | ⚠️ TIMEOUT (Internet-origin AP) | ✅ Works | Use NAT or VPC-origin AP |
| **VPC 内 + NAT Gateway** | ✅ Works | ✅ Works | Production recommended |
| **VPC 内 + VPC-origin AP + Gateway EP** | ✅ Expected per AWS docs | ✅ Works | Requires VPC-origin AP creation |

**Observed behavior**: In our environment (Internet-origin S3 AP), VPC Lambda with only a Gateway Endpoint timed out. AWS [documents](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html) that VPC-origin access points work with Gateway Endpoints for traffic originating within the bound VPC. The network origin cannot be changed after creation.

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
| S3 Event Notifications / EventBridge | ❌ Not supported | Use EventBridge Scheduler (polling + checkpointing) |
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

> **ONTAP CLI note**: ONTAP 9.11+ deprecates the `vserver` prefix on FPolicy commands (e.g., `vserver fpolicy` → `fpolicy`). Both forms work for backward compatibility. This project uses the deprecated form for compatibility with older ONTAP versions on FSx.

Reference: [AWS Docs — File access auditing](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)

### Vendor API key caching in Lambda

API keys are fetched from Secrets Manager once per Lambda execution context (cold start) and cached in a module-level variable. This avoids per-invocation Secrets Manager calls. The `_api_key_cache` pattern is intentional — do not refactor into per-request fetching.

### Bilingual documentation sync

Japanese (`docs/ja/`) is the primary language. English (`docs/en/`) must mirror the same heading structure and content. When modifying docs, always update both languages. Code examples are identical across languages.

## Vendor API Reference (Quick Lookup)

| Vendor | Endpoint | Auth Header | Max Batch | Firehose | Notes |
|--------|----------|-------------|-----------|----------|-------|
| Datadog | `https://http-intake.logs.{site}/api/v2/logs` | `DD-API-KEY: <key>` | 5MB / 1000 items | ✅ | |
| New Relic | `https://log-api.newrelic.com/log/v1` (US) | `Api-Key: <license>` | 1MB | ✅ | |
| Grafana/Loki | `https://otlp-gateway-prod-<region>.grafana.net/otlp` | Basic Auth (base64(ID:token)) | ~4MB recommended | ❌ | ✅ Verified via otlp_http exporter (NOT loki exporter) |
| Splunk | `https://<host>:8088/services/collector/event` | `Authorization: Splunk <token>` | No hard limit | ✅ (built-in) | |
| Elastic | `https://<cluster>/_bulk` | `Authorization: ApiKey <key>` | ~10MB recommended | ❌ | |
| Dynatrace | `https://<env>.live.dynatrace.com/api/v2/logs/ingest` | `Authorization: Api-Token <token>` | 1MB | ✅ | |
| Sumo Logic | `https://endpoint<N>.collection.sumologic.com/...` | Embedded in URL | 1MB | ❌ | |
| Honeycomb | `https://api.honeycomb.io` | `x-honeycomb-team: <hcaik_key>` | 5MB | ❌ | ✅ Verified via otlp_http exporter + x-honeycomb-dataset header |
| OTel (OTLP) | `http://<collector>:4318/v1/logs` | Configurable | Configurable | ❌ | ✅ Verified: Datadog + Grafana + Honeycomb multi-backend (0.152.0) |

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
- Commit real AWS account IDs, resource IDs, or IP addresses (use placeholders)
- Commit screenshots without running `mask_screenshots.py`

## Security & Privacy (Public Repository)

This is a **public repository**. All committed content is visible to anyone.

### Sensitive Data Rules

| Data Type | Placeholder | Example |
|-----------|-------------|---------|
| AWS Account ID | `123456789012` | `arn:aws:s3:us-east-1:123456789012:accesspoint/...` |
| Secret ARN suffix | `-XXXXXX` | `secret:fsxn-datadog-api-key-XXXXXX` |
| FSx File System ID | `fs-0123456789abcdef0` | — |
| SVM ID | `svm-0123456789abcdef0` | — |
| VPC/Subnet/SG IDs | `vpc-0123456789abcdef0` | — |
| Private IPs | `10.0.x.x` or `<management-ip>` | — |
| Public IPs | `<bastion-ip>` | — |
| SSH key paths | `<your-ssh-key.pem>` | — |
| SVM UUID | `<svm-uuid>` | — |

### Pre-Push Checklist

```bash
# 1. Check for real account IDs in tracked files
git ls-files | xargs grep -l "<your-account-id>" 2>/dev/null && echo "FAIL" || echo "PASS"

# 2. Check .kiro/ is not tracked
git ls-files .kiro/ | wc -l  # Should be 0

# 3. Check docs/blog/ is not tracked
git ls-files docs/blog/ | wc -l  # Should be 0

# 4. Mask screenshots before committing
python3 docs/screenshots/mask_screenshots.py

# 5. Run tests
python -m pytest integrations/datadog/tests/ -q
```

### .gitignore Protected Paths

These paths MUST remain in `.gitignore`:
- `.kiro/` — IDE steering files (contain environment-specific info)
- `docs/blog/` — Draft articles (published via dev.to, not GitHub)
- `.env` — API keys and credentials
- `*.pem` — SSH keys

### Scripts Must Be Environment-Agnostic

All scripts use environment variables with sensible defaults:
- `AWS_REGION` — defaults to `ap-northeast-1` but overridable
- `AWS_ACCOUNT_ID` — dynamically resolved via `aws sts get-caller-identity`
- `ONTAP_MGMT_IP` — required, no default (user must set)
- `SVM_UUID` — required, no default (user must set)
- `BASTION_IP` / `BASTION_KEY` — optional (only if ONTAP is behind bastion)

## Key Files

- `integrations/datadog/lambda/handler.py` — Reference implementation (audit log path)
- `integrations/datadog/lambda/fpolicy_handler.py` — FPolicy handler (SQS + EventBridge dual-format)
- `integrations/datadog/template.yaml` — Reference CloudFormation template (audit log)
- `integrations/datadog/template-ems-fpolicy.yaml` — EMS + FPolicy Lambda (with SQS event source mapping)
- `shared/lambda-layers/log-parser/python/fsxn_log_parser/parser.py` — EVTX/XML parser
- `shared/lambda-layers/s3ap-reader/python/s3ap_reader/reader.py` — S3 AP utility
- `shared/templates/iam-base-roles.yaml` — IAM role pattern
- `shared/templates/fpolicy-server-fargate.yaml` — FPolicy Fargate stack (ECS + SQS)
- `shared/fpolicy-server/build-and-push.sh` — ECR image build (linux/amd64 required)
- `shared/scripts/pre-push-security-check.sh` — Security scan before push
- `shared/scripts/fpolicy-fargate-control.sh` — FPolicy Fargate start/stop/status
- `shared/scripts/fpolicy-update-engine-ip.sh` — ONTAP Engine IP auto-update
- `docs/screenshots/mask_screenshots.py` — Screenshot masking (PII removal)

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
- FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → Vendor (SQS event source mapping)
- FPolicy uses a proprietary binary protocol over TCP (NOT HTTP/HTTPS)
- ONTAP connects directly to Fargate task IP (not via NLB)
- Fargate task IP changes on restart — ONTAP External Engine must be updated

Two patterns exist:
- **Pattern A (existing FSx ONTAP)**: Deploy prerequisites.yaml → enable audit → deploy vendor stack
- **Pattern B (from scratch)**: Create FSx ONTAP → then Pattern A

Full guide: `docs/ja/prerequisites.md` / `docs/en/prerequisites.md`

## Adding a New Vendor Integration

1. Create directory: `mkdir -p integrations/<vendor>/{lambda,scripts,docs/{ja,en},tests}`
2. Copy reference: use `integrations/grafana/` as the template (most complete)
3. Implement `lambda/handler.py` with vendor-specific API formatting
4. Create `template.yaml` following the CloudFormation structure in steering
5. Create `template-ems.yaml` for EMS webhook Lambda
6. Create `template-fpolicy.yaml` for FPolicy EventBridge Lambda
7. Write bilingual docs: `docs/ja/setup-guide.md` and `docs/en/setup-guide.md`
8. Add pytest tests with mocked API responses
9. Create `scripts/deploy.sh` (env-var driven, no hardcoded values)
10. Create `scripts/cleanup.sh` as a thin wrapper calling `shared/scripts/cleanup-vendor.sh`
11. Update root `README.md` vendor table (change 🚧 to ✅)
12. Update `docs/{ja,en}/vendor-comparison.md`

### Cleanup Script Template

Each vendor's `scripts/cleanup.sh` should be a thin wrapper:

```bash
#!/bin/bash
# Clean up <Vendor> integration resources.
set -euo pipefail

export STACK_PREFIX="${STACK_PREFIX:-fsxn-<vendor>}"
export SECRET_NAME="${SECRET_NAME:-<vendor>/fsxn-credentials}"
export VENDOR_NAME="<Vendor Name>"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh" "$@"
```

The shared script (`shared/scripts/cleanup-vendor.sh`) handles:
- Dependency-safe deletion order (API Gateway before Lambda)
- DELETE_FAILED state detection and guidance
- Optional Lambda Layer, Secret, and S3 data cleanup
- `--all` flag for complete teardown
- `-y` flag for CI/CD non-interactive mode

### Deletion Order (Critical)

CloudFormation stacks MUST be deleted in this order:

```
1. ${STACK_PREFIX}-fpolicy       (no external dependencies)
2. ${STACK_PREFIX}-ems-webhook   (API Gateway references EMS Lambda ARN)
3. ${STACK_PREFIX}-ems           (safe after API Gateway is gone)
4. ${STACK_PREFIX}-integration   (independent)
```

If you delete the EMS Lambda (step 3) before the API Gateway (step 2), CloudFormation will fail with a resource-in-use error.

## Commit Convention

```
feat: add New Relic integration
fix: handle empty EVTX files in log parser
docs: update Datadog setup guide for AP1 region
test: add batch splitting edge case tests
chore: update cfn-lint to v1.x
```

Conventional Commits format. English only. Keep subject under 72 characters.
