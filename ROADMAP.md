# Roadmap

## Current State (May 2026)

All 9 vendor integrations are E2E verified. The project provides a complete serverless observability pattern library for FSx for ONTAP.

## Phase 1: Foundation (Completed)

- [x] 9 vendor integrations (Datadog, New Relic, Splunk, OTel Collector, Grafana, Elastic, Dynatrace, Sumo Logic, Honeycomb)
- [x] 3 event sources (Audit logs, EMS webhooks, FPolicy)
- [x] CloudFormation templates for all integrations
- [x] Bilingual documentation (ja/en)
- [x] CI/CD pipeline (lint, test, cfn-lint, security scan)
- [x] dev.to blog series (Parts 1-12)
- [x] Partner assets (Solution Brief, PoC Proposal, Workshop Agenda)

## Phase 2: Production Hardening (In Progress)

Target: Q3 2026

- [x] Pipeline SLO definitions with Go/No-Go criteria
- [x] Data Classification Guide (PII field mapping + handling patterns)
- [x] Operational Runbooks (DLQ replay, Lambda errors, checkpoint staleness)
- [x] Workshop Hands-On Guide (half-day)
- [x] Full CI coverage (all 9 vendors + shared layers + coverage report)
- [x] S3 AP read throughput benchmark (methodology + reference results)
- [x] Retention policy matrix (regulation-to-vendor mapping)
- [x] Secrets Manager auto-rotation sample
- [x] cfn-guard rules refinement (critical rules blocking)
- [x] Japanese documentation sync verification script
- [x] Cost validation template (estimated vs actual)
- [ ] Cost validation data (requires 1 month of production billing)

## Phase 3: Enterprise Features (Planned)

Target: Q4 2026

- [x] Multi-account deployment pattern (AWS Organizations + StackSets)
- [x] Cross-region replication for audit log DR
- [x] DynamoDB object ledger (per-object processing state)
- [x] SQS buffering pattern (backpressure handling)
- [x] Poison-pill auto-skip with alerting
- [x] OTel Collector PII redaction cookbook (per-regulation)
- [x] Compliance evidence pack template (ISMAP, FISC, SOC2)
- [ ] Cost model validation (estimated vs actual billing comparison)

## Phase 4: Community & Ecosystem (Planned)

Target: 2027 H1

- [ ] AWS Solutions Library submission
- [ ] SAM (Serverless Application Model) packaging
- [ ] AWS Marketplace listing (partner-delivered)
- [ ] Terraform module equivalents
- [ ] CDK construct library
- [x] Community contribution guidelines (CONTRIBUTING.md)
- [ ] GitHub Discussions for Q&A
- [ ] Integration test suite with LocalStack

## Blog Series Plan

| Part | Title | Status |
|------|-------|--------|
| 1-8 | Foundation series | Published |
| 9 | Data Sovereignty with Elastic | Draft |
| 10 | High-Cardinality Analysis with Honeycomb | Draft |
| 11 | AI-Powered Root Cause with Dynatrace | Draft |
| 12 | JP Region with Sumo Logic | Draft |
| 13 | 9 Vendors, One Architecture: Lessons Learned (series finale) | Draft |
| 14 | Production Hardening: SLOs, Runbooks, and Data Classification | Planned |
| 15 | Multi-Account Deployment with AWS Organizations | Planned (Phase 3) |

## Contributing

This project welcomes contributions. Priority areas:
- Additional vendor integrations (Axiom, Mezmo, Coralogix)
- Terraform equivalents of CloudFormation templates
- Localization (Korean, Chinese)
- Benchmark data from different FSx for ONTAP configurations

See the repository issues for specific tasks.
