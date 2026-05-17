# FSx for ONTAP Observability Integrations

🌐 [日本語](../ja/README.md) | **English** (this page)

---

## Overview

EC2-free observability integrations for Amazon FSx for NetApp ONTAP via FSx for ONTAP S3 Access Points.

## Architecture Pattern

```
FSx ONTAP → Enable audit logging → Output to audit volume
audit volume → FSx for ONTAP S3 Access Point for S3 API access
EventBridge Scheduler → Lambda → Vendor API endpoint

EMS: ONTAP → Webhook → API Gateway → Lambda → Vendor API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → Vendor API
```

## Supported Integrations

| Vendor | Status | Description |
|--------|--------|-------------|
| [Datadog](../../integrations/datadog/) | ✅ E2E verified | Logs API v2 via Lambda |
| [New Relic](../../integrations/new-relic/) | 🧪 Implementation ready | Log API v1 via Lambda |
| [Splunk (Serverless)](../../integrations/splunk-serverless/) | 🧪 Implementation ready | HEC via Lambda (replaces EC2 pattern) |
| [OTel Collector](../../integrations/otel-collector/) | 🧪 Implementation ready | Vendor-neutral OTLP/HTTP |
| [Grafana Cloud](../../integrations/grafana/) | 🧪 Implementation ready | Loki Push API via Lambda |
| [Elastic](../../integrations/elastic/) | 🧪 Implementation ready | Elasticsearch Bulk API |
| [Dynatrace](../../integrations/dynatrace/) | 🧪 Implementation ready | Log Ingest API v2 |
| [Sumo Logic](../../integrations/sumo-logic/) | 🧪 Implementation ready | HTTP Source |
| [Honeycomb](../../integrations/honeycomb/) | 🧪 Implementation ready | Events Batch API |

Status:
- ✅ **E2E verified** — Deployed and validated with real FSx for ONTAP audit logs
- 🧪 **Implementation ready** — Code and CloudFormation available; E2E validation pending

## Background

The existing Splunk integration blog ([AWS Blog](https://aws.amazon.com/blogs/storage/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) uses an EC2-based approach (syslog-ng + Universal Forwarder).

This project provides an **EC2-free** alternative using Lambda + ECS Fargate.

## Business Outcomes

- Reduce EC2 collector operations (no patching, no agent management)
- Standardize audit log delivery across observability vendors
- Improve file access behavior visibility
- Enable faster security response using ONTAP-native telemetry

## Partner Positioning

This project helps partners modernize EC2-based FSx for ONTAP audit log collectors into an EC2-free, vendor-neutral observability pipeline.

Common customer scenarios:
- Replacing Splunk Universal Forwarder on EC2
- Modernizing audit visibility for enterprise file shares (departmental file servers, application interface directories such as SAP/Oracle/SQL Server adjacent shares, VDI/EUC home directories, engineering and design repositories)
- Integrating FSx for ONTAP with existing SIEM / observability platforms
- Preparing for ransomware detection workflows using ONTAP telemetry

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

# 4. Enable FSx ONTAP audit logging (dry run)
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

## Teardown

```bash
# Remove vendor integration stack
aws cloudformation delete-stack \
  --stack-name fsxn-datadog-integration \
  --region ap-northeast-1

# Remove prerequisites stack (if no other vendor stacks depend on it)
aws cloudformation delete-stack \
  --stack-name fsxn-observability-prerequisites \
  --region ap-northeast-1

# ONTAP audit logging remains active — disable separately if needed:
# vserver audit disable -vserver <svm-name>
```

> **Note**: Deleting the stack does not affect ONTAP audit logging or existing data on the FSx volume.

## Documentation

- [Prerequisites & Deployment Guide](prerequisites.md)
- [S3 AP Specification & Troubleshooting](s3ap-fsxn-specification.md)
- [Architecture](architecture.md)
- [Event Sources Guide](event-sources.md)
- [Vendor Comparison](vendor-comparison.md)
- [Demo Scenarios](demo-scenarios.md)
- [Operational Guide](operational-guide.md)
- [ONTAP Audit Setup Guide](ontap-audit-setup.md)
- [Minimum Test Path](quick-start-minimum.md)
- [Detection Use Cases](detection-use-cases.md)
- [Normalized Event Schema](normalized-event-schema.md)

## Tech Stack

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (log processing) + TypeScript (API integration)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (bilingual EN/JA)

## License

MIT
