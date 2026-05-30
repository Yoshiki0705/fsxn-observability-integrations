# Data Residency Matrix

> This document provides technical guidance on data flow destinations. It does not constitute legal, compliance, or regulatory advice. Consult your legal/compliance team for authoritative guidance on cross-border data transfer requirements (GDPR, APPI, PDPA, etc.).

## What Data Is Sent

FSx for ONTAP audit logs may contain the following data categories:

| Data Category | Examples | Sensitivity Level |
|--------------|---------|-------------------|
| User identities | `admin@corp.local`, `DOMAIN\username` | PII (jurisdiction-dependent) |
| File paths | `/vol/hr/salary-2026.xlsx`, `/vol/legal/contract.pdf` | Business confidential (path names may reveal content nature) |
| Client IP addresses | Internal IPs (RFC 1918) | Internal network topology |
| Timestamps | File access times | Behavioral metadata |
| Operation types | ReadData, WriteData, Delete | Activity metadata |
| SVM names | `svm-prod-finance` | Infrastructure metadata |

## Vendor Data Residency Options

| Vendor | Available Regions | Self-Hosted Option | Data Sovereignty Notes |
|--------|------------------|-------------------|----------------------|
| **Datadog** | US1 (Virginia), US3, US5, EU1 (Frankfurt), AP1 (Tokyo), AP2, US1-FED (GovCloud) | ❌ | AP1 (Tokyo) available for Japan residency |
| **New Relic** | US (Oregon), EU (Frankfurt), JP (Tokyo — July 2026) | ❌ | JP region launching July 2026; US or EU only until then |
| **Grafana Cloud** | US (multiple), EU (multiple), AP (Sydney, Singapore); Tokyo on Dedicated tier only | ✅ (Grafana OSS + Loki) | Self-hosted keeps data in your VPC; Free/Pro tiers limited to US/EU |
| **Splunk** | Splunk Cloud: US, EU, AU, custom | ✅ (Splunk Enterprise) | Self-managed keeps data in your infra |
| **Elastic** | Elastic Cloud: US, EU, AP (Tokyo, Sydney, Singapore) | ✅ (Self-hosted) | Self-hosted = full data sovereignty |
| **Dynatrace** | SaaS: US, EU, AP (Sydney, Singapore) | ✅ (Managed / ActiveGate) | Managed deployment = your infra |
| **Sumo Logic** | US, EU (Dublin, Frankfurt), AU (Sydney), JP (Tokyo) | ❌ | JP deployment available |
| **Honeycomb** | US only | ❌ | No non-US option currently |
| **OTel Collector** | N/A (self-hosted) | ✅ (always) | Data stays in your VPC until exported to backend |

## Decision Framework

### Step 1: Classify your data

- Does the audit log contain PII (usernames, email addresses)?
- Are file paths considered business confidential?
- Does your organization have data localization requirements?

### Step 2: Identify regulatory requirements

| Regulation | Key Requirement | Impact on Vendor Selection |
|-----------|----------------|---------------------------|
| GDPR (EU) | Data must stay in EU or have adequate transfer mechanism | Select EU region or self-hosted |
| APPI (Japan) | Cross-border transfer requires consent or equivalent protection | Prefer JP/AP region vendors |
| PDPA (Singapore) | Transfer requires comparable protection | Select AP region |
| HIPAA (US) | BAA required for PHI | Verify vendor BAA availability |
| SOX / PCI DSS | Audit trail integrity | Any vendor with immutable logs |

### Step 3: Select vendor + region

```
If data localization required:
  → Self-hosted (Elastic, Grafana, Splunk, Dynatrace Managed)
  → OR vendor with local region (Datadog AP1, Sumo Logic JP)

If no strict localization:
  → Any vendor with acceptable security posture
  → Prefer region closest to FSx for ONTAP for latency
```

### Step 4: Document the decision

Record in your PoC plan:
- [ ] Data classification completed
- [ ] Regulatory requirements identified
- [ ] Vendor region selected with justification
- [ ] Cross-border transfer mechanism documented (if applicable)
- [ ] Compliance team sign-off obtained

## PII Redaction Options

If you need to send logs externally but must redact PII:

| Approach | How | Complexity |
|----------|-----|-----------|
| OTel Collector `transform` processor | Regex replace on username/path fields | Medium |
| Lambda-level redaction | Modify handler to mask fields before sending | Low |
| Grafana Alloy pipeline | Built-in relabeling and field dropping | Medium |
| Don't send PII fields | Remove user/path from payload entirely | Low (but reduces value) |

Example OTel Collector redaction:
```yaml
processors:
  transform:
    log_statements:
      - context: log
        statements:
          - replace_pattern(body, "UserName\":\"[^\"]+\"", "UserName\":\"[REDACTED]\"")
```

## Related Documents

- [Security Best Practices](security-best-practices.md)
- [Governance and Compliance](governance-and-compliance.md)
- [Vendor Comparison](vendor-comparison.md)
