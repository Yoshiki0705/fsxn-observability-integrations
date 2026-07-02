# FSx for ONTAP Observability Integrations

🌐 [日本語](../ja/README.md) | **English** (this page)

> This is a community reference implementation and not an official AWS service feature or compliance attestation. Validate all configurations, costs, and compliance requirements in your own environment.

---

## Overview

EC2-free observability integrations for Amazon FSx for NetApp ONTAP via FSx for ONTAP S3 Access Points. Ship audit logs, EMS events, and FPolicy file operations to 9 observability vendors — all serverless.

## Choose Your Path

| Goal | Recommended Path | Why |
|---|---|---|
| First validation | Audit poller only | Fastest way to prove read path, delivery, checkpoint, and DLQ |
| GUI-based management | NetApp Console + System Manager | No CLI required; audit, quota, FSA all in browser |
| Single observability backend | Direct vendor integration | Fewer moving parts |
| Grafana Cloud quickstart | Direct OTLP Gateway | Native OTLP path to Loki |
| Multi-backend / redaction / routing | OTel Collector or Grafana Alloy | Move cross-cutting pipeline concerns out of Lambda |
| Higher reliability | SQS + DynamoDB ledger + Collector/Alloy | Backpressure, replay, batching, durable state |
| Partner PoC | Partner Solution Brief + PoC Checklist | Clear scope, deliverables, and responsibility boundaries |

## Recommended First 30 Minutes

1. Read "Choose Your Path" above to identify your target integration
2. Run unit tests with sample payloads: `python -m pytest integrations/datadog/tests/ -v`
3. Review the [PoC Success Criteria](poc-success-criteria.md) for your target integration
4. Deploy audit-only path in a sandbox account (see Quick Start below)
5. Confirm: one log record arrives, checkpoint advances, DLQ remains empty

## Architecture Pattern

```
FSx for ONTAP → Enable audit logging → Output to audit volume
audit volume → FSx for ONTAP S3 Access Point for S3 API access
EventBridge Scheduler → Lambda → Vendor API endpoint

EMS: ONTAP → Webhook → API Gateway → Lambda → Vendor API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → Vendor API
```

### Trigger Model Note

FSx for ONTAP S3 Access Points do **NOT** support S3 Event Notifications or EventBridge object-level events. This project uses:

- **EventBridge Scheduler polling**: Periodically invokes Lambda with SSM Parameter Store checkpointing to track processed files
- **CloudTrail data events**: Documented alternative for near-real-time triggering
- **Regular S3 bucket + S3 Event Notifications**: For test data validation

## Supported Integrations

| Vendor | Status | Description |
|--------|--------|-------------|
| [Datadog](../../integrations/datadog/) | ✅ E2E verified | Logs API v2 via Lambda |
| [New Relic](../../integrations/new-relic/) | ✅ E2E verified | Log API v1 via Lambda |
| [Splunk (Serverless)](../../integrations/splunk-serverless/) | ✅ E2E verified | HEC via Lambda (replaces EC2 pattern) |
| [OTel Collector](../../integrations/otel-collector/) | ✅ E2E verified | Vendor-neutral OTLP/HTTP (Datadog + Grafana + Honeycomb) |
| [Grafana Cloud](../../integrations/grafana/) | ✅ E2E verified | OTLP Gateway via Lambda (Loki Push API fallback) |
| [Elastic](../../integrations/elastic/) | ✅ E2E verified | Elasticsearch Bulk API |
| [Dynatrace](../../integrations/dynatrace/) | ✅ E2E verified | Log Ingest API v2 |
| [Sumo Logic](../../integrations/sumo-logic/) | ✅ E2E verified | HTTP Source |
| [Honeycomb](../../integrations/honeycomb/) | ✅ E2E verified | Events Batch API |
| [CrowdStrike Falcon LogScale](../../integrations/crowdstrike/) | ✅ HEC verified (via Splunk) | HEC via Lambda (Splunk HEC compatible) |
| [NetApp Console / System Manager](../../integrations/netapp-console/) | ✅ Verified | GUI management + FSA (File System Analytics) |

Status:
- ✅ **E2E verified** — Deployed and validated with real FSx for ONTAP audit logs

## Background

The existing Splunk integration blog ([AWS Blog](https://aws.amazon.com/blogs/storage/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) uses an EC2-based approach (syslog-ng + Universal Forwarder).

This project provides an **EC2-free** alternative using Lambda + ECS Fargate.

## Business Outcomes

**Before → After**:
- 🔴 2x EC2 always-on (patching, agent updates, ~$66/month) → 🟢 Zero-ops serverless pipeline (~$6/month, pay-per-use)
- 🔴 Audit logs locked inside FSx volume → 🟢 Instantly searchable and alertable in existing SIEM/Observability
- 🔴 Hours from ransomware detection to response → 🟢 Alert fired within 30 seconds via EMS/FPolicy

**Measurable outcomes**:
- Eliminate EC2 collector operations (no patching, no agent management)
- Standardize audit log delivery across observability vendors
- Improve file access behavior visibility
- Enable faster security response using ONTAP-native telemetry

## Partner Positioning

This project helps partners modernize EC2-based FSx for ONTAP audit log collectors into an EC2-free, vendor-neutral observability pipeline.

Common customer scenarios:
- Replacing Splunk Universal Forwarder on EC2
- Modernizing audit visibility for enterprise file shares
- Integrating FSx for ONTAP with existing SIEM / observability platforms
- Preparing for ransomware detection workflows using ONTAP telemetry

## Try with Sample Data

If you do not have FSx for ONTAP audit logs yet, use the sample payloads under `examples/`:

```bash
bash scripts/generate-splunk-hec-payload.sh --count 5
bash scripts/generate-otlp-payload.sh --count 5
```

See [`examples/`](../../examples/) for pre-built sample audit, EMS, and FPolicy event payloads.

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/Yoshiki0705/fsxn-observability-integrations.git
cd fsxn-observability-integrations

# 2. Install dependencies
npm install

# 3. Deploy prerequisites (EventBridge Scheduler + checkpoint)
aws cloudformation deploy \
  --template-file shared/templates/prerequisites.yaml \
  --stack-name fsxn-observability-prerequisites \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --capabilities CAPABILITY_IAM

# 4. Enable FSx for ONTAP audit logging (dry run)
bash shared/scripts/ontap-audit-setup.sh \
  --endpoint <management-ip> --svm <svm-name> --dry-run

# 5. Deploy vendor integration (example: Datadog)
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
    DatadogSite=datadoghq.com \
  --capabilities CAPABILITY_NAMED_IAM
```

> 📝 See the [Prerequisites Guide](prerequisites.md) for detailed instructions.

## Quick Validation

After deploying a vendor integration stack:

```bash
# 1. Confirm Scheduler is invoking Lambda
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-300)*1000))") \
  --region ap-northeast-1

# 2. Confirm DLQ is empty (no failed events)
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names All \
  --query 'Attributes.ApproximateNumberOfMessages'

# 3. Search in your observability platform
#    Datadog: source:fsxn
#    Splunk:  index=fsxn_audit
#    Grafana: {source="fsxn"}
```

## Production Readiness Levels

### Level 0: Local Validation
- Sample payload parsing and unit tests
- OTLP / HEC payload snapshot tests

### Level 1: Quickstart
- Single audit poller with SSM checkpoint
- EventBridge Scheduler + DLQ
- Direct vendor delivery

### Level 2: Operational PoC
- Dashboard and alerts configured
- Replay runbook documented
- Cost estimate produced
- Webhook security enabled

### Level 3: Production Baseline
- DynamoDB object ledger
- SQS buffering
- Poison-pill handling
- Pipeline SLO monitoring
- Security review completed

### Level 4: Enterprise Pipeline
- OTel Collector or Grafana Alloy
- Redaction and routing rules
- Multi-backend export
- Compliance evidence pack

## Teardown

```bash
aws cloudformation delete-stack --stack-name fsxn-datadog-integration --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-observability-prerequisites --region ap-northeast-1
# ONTAP audit logging remains active — disable separately if needed:
# vserver audit disable -vserver <svm-name>
```

> **Note**: Deleting the stack does not affect ONTAP audit logging or existing data on the FSx volume.

## GUI Management (NetApp Console / System Manager)

ONTAP System Manager is accessible via NetApp Console and enables browser-based management without CLI:

- Audit log configuration and management
- Qtree quota (capacity limit) configuration
- File System Analytics (FSA) — file access trend visualization
- Activity Tracking — real-time file operation monitoring
- Volume and share management

> **Access path**: [NetApp Console](https://console.netapp.com/) → Systems → SERVICES → "Open" (System Manager)
>
> **Cost**: NetApp Console Link (Lambda) ~$0.008/month. System Manager itself is free.

📖 [Management & Monitoring Decision Tree](decision-tree-management-monitoring.md)

📖 [System Manager GUI Guide](system-manager-gui-guide.md)

📖 [NetApp Console Integration](../../integrations/netapp-console/)

## Documentation

### Getting Started
- [Prerequisites & Deployment Guide](prerequisites.md)
- [Minimum Test Path](quick-start-minimum.md)
- [ONTAP Audit Setup Guide](ontap-audit-setup.md)

### Architecture & Design
- [Architecture](architecture.md)
- [Event Sources Guide](event-sources.md)
- [S3 AP Specification & Troubleshooting](s3ap-fsxn-specification.md)
- [Normalized Event Schema](normalized-event-schema.md)
- [Delivery Guarantee Patterns](delivery-guarantees.md)
- [Management & Monitoring Decision Tree](decision-tree-management-monitoring.md)
- [System Manager GUI Guide](system-manager-gui-guide.md)

### Operations & Production
- [Pipeline SLO Definitions](pipeline-slo.md)
- [Operational Guide](operational-guide.md)
- [CloudWatch Log Alarm](cloudwatch-log-alarm.md)
- [Log Alarm Triggered Runbook](runbooks/log-alarm-triggered.md)
- [DLQ Replay Runbook](runbooks/dlq-replay.md)
- [Lambda Errors Runbook](runbooks/lambda-errors.md)
- [Checkpoint Staleness Runbook](runbooks/checkpoint-stale.md)
- [S3 AP Throughput Benchmark](s3ap-throughput-benchmark.md)
- [Cost Validation Template](cost-validation.md)

### Security & Compliance
- [Data Classification Guide](data-classification.md)
- [Retention Policy Matrix](retention-policy-matrix.md)
- [Compliance Evidence Pack](compliance-evidence-pack.md)
- [Security Review Checklist](security-review-checklist.md)
- [Webhook Security Guide](webhook-security.md)
- [Data Residency Matrix](data-residency.md)
- [Governance & Compliance](governance-and-compliance.md)

### Enterprise & Scale
- [Multi-Account Deployment (StackSets)](multi-account-deployment.md)
- [Cross-Region Replication (DR)](cross-region-replication.md)
- [OTel Collector PII Redaction Cookbook](../../integrations/otel-collector/docs/en/pii-redaction-cookbook.md)

### Partner & Workshop
- [Vendor Comparison](vendor-comparison.md)
- [Partner FAQ](partner-faq.md)
- [Partner Solution Brief](partner-solution-brief.md)
- [PoC Proposal Template](poc-proposal-template.md)
- [PoC Success Criteria](poc-success-criteria.md)
- [Workshop Hands-On Guide (Half Day)](workshop-hands-on-half-day.md)
- [Workshop Agenda](workshop-agenda.md)
- [Demo Scenarios](demo-scenarios.md)
- [Detection Use Cases](detection-use-cases.md)

## Tech Stack

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (log processing) + TypeScript (API integration)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (bilingual EN/JA)

## Related Projects

| Repository | Description |
|-----------|-------------|
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | 17 industry use cases with FPolicy event-driven pipeline |
| [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) | Data Lake and Lakehouse platform integrations via S3 Access Points |
| [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) | Access-aware Agentic RAG with Amazon Bedrock (CDK) |
| [fsx-ontap-lifecycle-management](https://github.com/Yoshiki0705/fsx-ontap-lifecycle-management) | 3-tier lifecycle management with S3 Glacier Deep Archive |

## License

MIT
