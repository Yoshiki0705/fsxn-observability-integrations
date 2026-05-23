# PoC Proposal Template: FSx for ONTAP Observability Integration

> Copy this template and fill in customer-specific details for each engagement.

---

## 1. Executive Summary

**Customer**: [Customer Name]
**Date**: [YYYY-MM-DD]
**Prepared by**: [Partner/SA Name]

**Objective**: Validate serverless delivery of FSx for ONTAP audit logs to [Vendor Name], replacing [current approach / filling visibility gap].

**Expected outcome**: Confirm that audit log events are queryable in [Vendor] within [X] minutes of file access, with zero EC2 infrastructure.

---

## 2. Business Context

### Customer Challenge
[Describe the specific customer pain point in 2-3 sentences]

### Expected Business Value
| Metric | Current State | Target State | Measurement Method |
|--------|--------------|-------------|-------------------|
| Operational cost | [e.g., $66/month for EC2] | [e.g., ~$6/month serverless] | AWS billing comparison |
| Time to detect anomaly | [e.g., hours/manual] | [e.g., <30 seconds automated] | Alert timestamp - event timestamp |
| Patching burden | [e.g., monthly OS + agent] | [e.g., zero] | Maintenance window count |
| Compliance coverage | [e.g., partial/none] | [e.g., full audit trail] | Audit report completeness |

---

## 3. Scope

### In Scope
- [ ] Audit log delivery (S3 AP → Lambda → [Vendor])
- [ ] EMS webhook delivery (ONTAP → API Gateway → Lambda → [Vendor])
- [ ] FPolicy real-time events (ONTAP → Fargate → SQS → Lambda → [Vendor])
- [ ] Dashboard creation
- [ ] Alert configuration
- [ ] Cost estimate for production volume

### Out of Scope
- [ ] FSx for ONTAP provisioning (assumed existing)
- [ ] Vendor platform procurement/licensing
- [ ] Production deployment (separate phase)
- [ ] Compliance certification
- [ ] Custom log transformation beyond standard schema

---

## 4. Success Criteria

### Level 1: Minimum (Must achieve)
- [ ] One audit log record arrives in [Vendor] and is queryable
- [ ] SSM checkpoint advances after successful delivery
- [ ] DLQ remains empty
- [ ] Deploy and delete complete cleanly

### Level 2: Operational (Should achieve)
- [ ] Dashboard shows log volume and error rate
- [ ] Alert fires on simulated failure
- [ ] Cost estimate produced for [X] GB/month production volume

### Level 3: Go/No-Go (Stretch)
- [ ] Delivery latency < [X] minutes measured
- [ ] Secrets rotation tested
- [ ] DLQ replay procedure documented

---

## 5. Timeline

| Day | Activity | Owner | Deliverable |
|-----|----------|-------|-------------|
| 1 | Kickoff + environment access | Both | Access confirmed |
| 2 | Deploy prerequisites + vendor stack | Partner/SA | Stack deployed |
| 3 | Validate delivery + build dashboard | Partner/SA | First log confirmed |
| 4 | Alert config + failure testing | Partner/SA | Alert fires |
| 5 | Documentation + Go/No-Go review | Both | PoC Report |

---

## 6. RACI Matrix

| Activity | Customer | Partner/SA | Vendor |
|----------|----------|-----------|--------|
| Provide AWS account access | **R/A** | C | — |
| FSx ONTAP audit logging config | C | **R** | — |
| Vendor account + API key | **R/A** | C | I |
| CloudFormation deployment | I | **R/A** | — |
| Delivery validation | C | **R** | I |
| Dashboard/alert creation | C | **R** | — |
| Cost estimate review | **A** | **R** | C |
| Go/No-Go decision | **A** | C | I |
| Production deployment (if Go) | **A** | **R** | C |
| Ongoing operations | **R/A** | C | I |

**R** = Responsible, **A** = Accountable, **C** = Consulted, **I** = Informed

---

## 7. Prerequisites

### Customer Provides
- [ ] AWS account with FSx for ONTAP file system
- [ ] IAM permissions for CloudFormation deployment
- [ ] Audit logging enabled on target SVM (or permission to enable)
- [ ] Vendor platform account (or willingness to create free tier)
- [ ] Network access: Lambda can reach vendor API (NAT Gateway if VPC)

### Partner/SA Provides
- [ ] CloudFormation templates (from this repository)
- [ ] Deployment guidance and troubleshooting
- [ ] Dashboard and alert configuration
- [ ] PoC Report with findings and recommendations

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| S3 AP network timeout (VPC + Gateway EP only) | Medium | High | Deploy Lambda outside VPC or add NAT Gateway |
| Vendor API rate limiting | Low | Medium | Implement exponential backoff (built into Lambda code) |
| Audit log format mismatch | Low | Medium | Test with sample data before real logs |
| Cross-border data transfer concern | Medium | High | Review Data Residency Matrix, select appropriate region |
| PoC cost overrun | Low | Low | Use free-tier vendor, monitor billing daily |

---

## 9. Cost Estimate

### PoC Phase (1 week)

| Component | Estimated Cost |
|-----------|---------------|
| Lambda invocations | < $1 |
| EventBridge Scheduler | < $0.01 |
| Secrets Manager | ~$0.40 |
| S3 requests (read) | < $0.10 |
| Vendor ingestion | $0 (free tier) or ~$1 (Datadog) |
| **Total PoC** | **< $3** |

### Production Estimate (monthly)

| Log Volume | AWS Cost | Vendor Cost | Total |
|-----------|---------|-------------|-------|
| [X] GB/month | ~$[Y] | ~$[Z] | ~$[Total] |

---

## 10. Go/No-Go Criteria

| Criteria | Threshold | Measured By |
|----------|-----------|-------------|
| Delivery success rate | > 99% | DLQ depth = 0 over 24h |
| Delivery latency | < [X] minutes | Timestamp comparison |
| Monthly cost acceptable | < $[budget] | Cost estimate |
| Data residency acceptable | [Region] approved | Compliance team sign-off |
| Operational ownership assigned | Named owner | RACI confirmed |

### Decision

- [ ] **GO**: Proceed to production deployment
- [ ] **NO-GO**: Document blockers, define remediation, re-evaluate in [timeframe]
- [ ] **CONDITIONAL GO**: Proceed with [conditions/limitations]

---

## 11. Next Steps (if Go)

1. Production deployment plan (2 weeks)
2. Security review completion
3. Operational runbook finalization
4. Monitoring and alerting in production
5. Knowledge transfer to operations team

---

## Appendix

- [Partner Solution Brief](partner-solution-brief.md)
- [Vendor Comparison](vendor-comparison.md)
- [Data Residency Matrix](data-residency.md)
- [Security Best Practices](security-best-practices.md)
- [PoC Success Criteria](poc-success-criteria.md)
