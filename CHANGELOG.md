# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Governance and compliance documentation (bilingual ja/en)
- Security review checklist (bilingual ja/en)
- PoC success criteria document (bilingual ja/en)
- Production readiness levels in README
- Choose your path decision guide in README
- Trigger model note explaining FSx S3 AP polling approach
- Sample payloads in examples/ directory (audit, EMS, FPolicy)
- cfn-guard rules for Lambda security and secrets management
- cfn-guard CI job in GitHub Actions
- Markdown link check CI job
- actionlint CI job
- Shared Python observability module (Lambda Powertools)
- Shared Python idempotency module (DynamoDB object ledger)
- Try with sample data section in README

### Changed
- README restructured as decision guide (not just implementation list)
- README Grafana Cloud description updated to OTLP Gateway primary
- Documentation section expanded with governance/security/PoC links

## [0.3.0] - 2026-05-15

### Added
- Splunk serverless integration (HEC via Lambda)
- Splunk EMS webhook handler
- Splunk Firehose alternative path template
- Splunk verification tooling and bilingual setup guides
- FPolicy → Splunk HEC delivery path
- EMS → Splunk HEC delivery path (ARP ransomware detection)

## [0.2.0] - 2026-04-20

### Added
- OTel Collector integration (vendor-neutral OTLP/HTTP)
- Triple-backend delivery verified (Datadog + Grafana Cloud + Honeycomb)
- OTel Collector production config with memory_limiter and sending_queue
- OTel config validation CI workflow
- Enterprise documentation suite (ADR, PoC checklist, security hardening, etc.)
- FPolicy server on ECS Fargate (TCP:9898 binary protocol)
- EMS webhook via API Gateway

## [0.1.0] - 2026-03-01

### Added
- Initial Datadog integration (Logs API v2 via Lambda)
- S3 Access Point reader Lambda Layer
- Log parser Lambda Layer (EVTX/JSON)
- EventBridge Scheduler polling with SSM checkpoint
- CloudFormation templates for prerequisites and Datadog
- Bilingual documentation (ja/en)
- CI pipeline (cfn-lint, pytest, jest)
- Security scan workflow
