# Retention Policy Matrix

## Overview

This matrix maps regulatory retention requirements to vendor-specific configuration. Use it to determine the minimum retention period for your FSx for ONTAP audit logs based on applicable regulations.

> **Governance caveat**: This matrix provides technical awareness for pipeline configuration. It does not constitute legal or compliance advice. Consult your compliance team for binding regulatory interpretation and your organization's specific retention obligations.

## Regulatory Retention Requirements

| Regulation | Scope | Minimum Retention | Notes |
|-----------|-------|-------------------|-------|
| **APPI** (Japan) | Personal information handling records | No explicit minimum; "necessary period" | Retention should align with purpose of use |
| **FISC Guidelines** (Japan Financial) | Financial system audit trails | 7 years (recommended) | FISC Security Guidelines for Computer Systems |
| **ISMAP** (Japan Gov Cloud) | Cloud service audit logs | 1 year minimum | ISMAP management criteria |
| **J-SOX** (Japan) | Internal control evidence | 7 years | Financial Instruments and Exchange Act |
| **GDPR** (EU) | Personal data processing records | No explicit minimum; "no longer than necessary" | Data minimization principle applies |
| **SOC 2** | Service organization controls | 1 year (audit period) | Typically 12-month observation window |
| **PCI DSS** | Payment card data access | 1 year (immediately available); 1 year archive | Requirement 10.7 |
| **HIPAA** (US Healthcare) | PHI access logs | 6 years | 45 CFR 164.530(j) |
| **SEC Rule 17a-4** (US Financial) | Electronic records | 3-6 years depending on record type | Broker-dealer requirements |

## Vendor Retention Configuration

| Vendor | Free Tier Retention | Paid Minimum | Maximum | Configuration Method |
|--------|-------------------|--------------|---------|---------------------|
| **Datadog** | 15 days | 15 days | Custom (Online Archive) | Organization Settings > Logs > Indexes |
| **New Relic** | 30 days | 30 days | Custom | Data Management > Retention |
| **Splunk** | N/A (self-hosted) | Configurable | Unlimited | indexes.conf: frozenTimePeriodInSecs |
| **Grafana Cloud** | 14 days | 14 days | 365 days | Loki retention_period per tenant |
| **Elastic** | 14 days (trial) | ILM configurable | Unlimited | Index Lifecycle Management policy |
| **Dynatrace** | 35 days | 35 days | 10 years (Grail) | Settings > Log Monitoring > Retention |
| **Sumo Logic** | 7 days | 30 days | 5000 days | Partition retention settings |
| **Honeycomb** | 60 days | 60 days | Custom | Dataset settings |
| **OTel Collector** | N/A (pass-through) | N/A | N/A | Backend-dependent |

## Regulation-to-Vendor Mapping

### FISC / J-SOX (7 years)

| Vendor | Achievable? | How |
|--------|------------|-----|
| Datadog | Yes | Online Archive (cold storage) |
| Splunk | Yes | Frozen bucket to S3 |
| Elastic | Yes | ILM: hot > warm > cold > frozen (S3) |
| Dynatrace | Yes | Grail storage (up to 10 years) |
| Sumo Logic | Yes | Partition retention up to 5000 days |
| Grafana/Honeycomb/New Relic | Partial | Archive to S3 separately for long-term |

**Recommended pattern for 7-year retention**:
```
Lambda -> Vendor (hot, 30-90 days) -> Vendor archive OR S3 Glacier (7 years)
```

### ISMAP / SOC 2 (1 year)

All vendors support 1-year retention in paid tiers. Free tiers are insufficient.

| Vendor | Paid Tier for 1 Year | Estimated Cost (10 GB/month) |
|--------|---------------------|------------------------------|
| Datadog | Standard plan | ~$150/month |
| Sumo Logic | Professional | ~$108/month |
| Elastic | Standard | ~$95/month |
| Dynatrace | Standard (Grail) | ~$25/month (DDU-based) |
| Grafana Cloud | Pro plan | ~$50/month |

### APPI / GDPR (Purpose-limited)

No fixed minimum — retain only as long as necessary for the stated purpose.

**Recommended approach**:
1. Define purpose: "Security investigation and compliance audit"
2. Set retention: 90 days hot + 1 year archive (typical)
3. Implement automatic deletion after retention period
4. Document the retention decision and review annually

## Dual-Path Architecture for Long Retention

For regulations requiring > 1 year retention, implement a dual-path:

```
FSx for ONTAP -> Lambda -> +-> Vendor (hot, 30-90 days) -- real-time queries
                       +-> S3 (archive, 7 years) -- compliance evidence
                               |
                               +-> S3 Standard (0-90 days)
                               +-> S3 Standard-IA (90 days - 1 year)
                               +-> S3 Glacier Deep Archive (1-7 years)
```

CloudFormation snippet for S3 lifecycle:
```yaml
AuditArchiveBucket:
  Type: AWS::S3::Bucket
  Properties:
    LifecycleConfiguration:
      Rules:
        - Id: TransitionToIA
          Status: Enabled
          Transitions:
            - StorageClass: STANDARD_IA
              TransitionInDays: 90
            - StorageClass: DEEP_ARCHIVE
              TransitionInDays: 365
          ExpirationInDays: 2555  # 7 years
```

## Implementation Checklist

- [ ] Identify applicable regulations for your organization
- [ ] Determine minimum retention period (use the matrix above)
- [ ] Configure vendor retention settings (paid tier if needed)
- [ ] Implement S3 archive path for long-term retention (if > vendor max)
- [ ] Set up S3 Lifecycle rules for cost optimization
- [ ] Enable S3 Object Lock for tamper-evidence (if required)
- [ ] Document retention policy and review schedule
- [ ] Configure alerts for approaching retention limits

## Related Documents

- [Data Classification Guide](data-classification.md)
- [Data Residency Matrix](data-residency.md)
- [Governance & Compliance](governance-and-compliance.md)
- [Pipeline SLO](pipeline-slo.md)
