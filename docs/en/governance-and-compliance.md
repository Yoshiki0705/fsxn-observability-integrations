# Governance and Compliance Considerations

## Scope

This repository provides observability pipeline patterns for FSx for ONTAP signals (audit logs, EMS events, FPolicy file operations). It does **not** replace workload-specific compliance controls, audit policy, backup, DR, or access governance.

The pipeline serves as an **observability and evidence layer** — complementing, not replacing, existing HA, backup/restore, and DR mechanisms.

## Responsibility Boundaries

| Area | Customer Responsibility | AWS Responsibility | Pipeline Scope |
|------|------------------------|-------------------|----------------|
| Audit log generation | Configure ONTAP audit policy | FSx for ONTAP service operation | Read and forward |
| Data classification | Classify audit log sensitivity | Encrypt at rest (SSE-FSx) | Transport only |
| Secrets management | Rotate API keys/tokens | Secrets Manager service | Retrieve and cache |
| Network security | VPC, Security Groups, NACLs | Physical infrastructure | Lambda/Fargate placement |
| Destination approval | Approve SaaS destinations | N/A | Deliver to approved endpoints |
| Retention policy | Define retention requirements | Storage durability | DLQ retention only |
| Change management | Review CloudFormation changes | Service availability | Template-based deployment |
| Incident response | Define escalation procedures | Service health notifications | Alert on delivery failures |

## Control Areas

### Data Classification
- Audit logs may contain file paths, usernames, IP addresses, and operation details
- EMS events may contain volume names, node identifiers, and alert conditions
- FPolicy events contain file operation details including full paths and client IPs
- Determine if these constitute PII or sensitive data under applicable regulations

### Secrets Management and Token Rotation
- All vendor API keys/tokens stored in AWS Secrets Manager
- Lambda caches tokens per execution context (cold start refresh)
- Rotation procedure: update Secrets Manager → next cold start picks up new value
- No plaintext secrets in CloudFormation parameters or environment variables

### IAM Least Privilege
- Lambda execution roles scoped to specific S3 Access Point ARN
- Secrets Manager access scoped to specific secret ARN
- SSM Parameter Store access scoped to checkpoint parameter path
- SQS permissions scoped to specific DLQ ARN
- No wildcard (*) resource permissions

### Evidence Retention
- CloudWatch Logs: configurable retention (default 30 days)
- DLQ messages: retained for replay investigation
- SSM checkpoint: tracks last processed audit file
- CloudFormation stack events: deployment audit trail

### Replay and Duplicate-Delivery Handling
- SSM checkpoint prevents re-processing of already-shipped files
- DLQ captures failed deliveries for manual replay
- Idempotency depends on backend deduplication (not guaranteed at pipeline level)
- DynamoDB object ledger (Level 3) provides exactly-once tracking

### Change Management
- All infrastructure defined as CloudFormation templates
- Pull request review for template changes
- CI validates templates with cfn-lint before deployment
- Stack update events provide deployment audit trail

### Operational Ownership and Escalation
- Define: who monitors DLQ depth, checkpoint age, delivery errors
- Define: escalation path for sustained delivery failures
- Define: approval process for adding new SaaS destinations
- Define: rotation schedule for vendor API tokens

## Review Checklist for Regulated Environments

Before deploying in regulated environments, confirm:

- [ ] Audit logs are classified per data classification policy
- [ ] Cross-border log transfer is acceptable (if SaaS destination is in another region/country)
- [ ] SaaS destination (Grafana Cloud, Datadog, Splunk, etc.) is approved by security team
- [ ] Retention and deletion requirements are defined for each log tier
- [ ] Replay procedure is approved by operations and security teams
- [ ] DLQ messages are reviewed as operational evidence
- [ ] IAM roles follow least-privilege principle (verified by security review)
- [ ] Secrets rotation procedure is documented and tested
- [ ] CloudFormation templates are reviewed for compliance (cfn-guard rules)
- [ ] Monitoring and alerting covers delivery failures, checkpoint staleness, and DLQ depth

## Applicable Frameworks

This pipeline pattern can support evidence requirements for:
- **AWS Well-Architected Framework** — Operational Excellence and Security pillars
- **SOC 2** — Monitoring and logging controls
- **ISO 27001** — A.12.4 Logging and monitoring
- **FISC** (金融情報システムセンター) — Audit trail requirements
- **ISMAP** — Cloud service security evaluation

> **Note**: Framework compliance requires holistic assessment beyond this pipeline. This document identifies where the pipeline contributes to control objectives.

## Related Documents

- [Security Review Checklist](security-review-checklist.md)
- [PoC Success Criteria](poc-success-criteria.md)
- [Delivery Guarantee Patterns](delivery-guarantees.md)
- [Operational Guide](operational-guide.md)
