# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Governance and compliance review guides (bilingual ja/en)
- Security review checklists (bilingual ja/en)
- PoC success criteria and production readiness levels
- CI policy documentation with cfn-guard adoption roadmap (bilingual ja/en)
- cfn-guard policy checks in GitHub Actions (non-blocking)
- Markdown link check and actionlint CI jobs
- Sample payloads for audit, EMS, and FPolicy validation in examples/
- Shared Python observability module (Lambda Powertools logger/metrics/tracer)
- Shared Python object ledger module (DynamoDB-backed idempotent processing)
- Choose your path decision guide in README
- Recommended first 30 minutes section in README
- Try with sample data section in README
- Community disclaimer in README

### Changed
- README restructured as decision guide with production readiness levels
- Clarified FSx for ONTAP S3 Access Point trigger model (polling, not event-driven)
- Updated Grafana Cloud path to OTLP Gateway primary, Loki Push API fallback
- Reworded ObjectLedger semantics as idempotent object processing and duplicate suppression
- Added compliance disclaimer to governance docs (not an attestation)
- Updated .markdown-link-check.json with flaky link mitigation

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
