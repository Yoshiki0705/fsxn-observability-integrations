# Data Classification Guide for FSx for ONTAP Audit Logs

🌐 [日本語](../ja/data-classification.md) | **English** (this page)

## Overview

FSx for ONTAP audit logs contain information that may be classified as Personally Identifiable Information (PII) or sensitive business data. This guide identifies which fields require attention and provides recommended handling patterns.

> **Important**: This guide provides technical classification for pipeline design decisions. It does not replace a formal data classification assessment by your organization's data protection officer or compliance team.

## Field Classification Matrix

### Audit Log Fields

| Field | Example Value | Classification | PII Risk | Recommended Handling |
|-------|--------------|---------------|----------|---------------------|
| `UserName` | `admin@corp.local` | **PII** | High | Hash or pseudonymize in non-production |
| `ObjectName` / `path` | `/vol/hr/employee-records/salary.xlsx` | **Sensitive** | Medium | Path may reveal business context |
| `ClientIP` / `source.ip` | `10.0.x.x` | **Internal** | Low | Acceptable in most contexts |
| `EventID` | `4663` | **Non-sensitive** | None | No handling needed |
| `Operation` | `ReadData` | **Non-sensitive** | None | No handling needed |
| `Result` | `Success` / `Failure` | **Non-sensitive** | None | No handling needed |
| `SVMName` | `svm-prod-01` | **Internal** | None | May reveal infrastructure naming |
| `Timestamp` | `2026-01-15T12:00:00Z` | **Non-sensitive** | None | No handling needed |

### EMS Event Fields

| Field | Example Value | Classification | PII Risk |
|-------|--------------|---------------|----------|
| `event_name` | `arw.volume.state` | Non-sensitive | None |
| `severity` | `alert` | Non-sensitive | None |
| `message` | Free-text ONTAP message | **Review required** | Low-Medium |

### FPolicy Event Fields

| Field | Example Value | Classification | PII Risk |
|-------|--------------|---------------|----------|
| `user` | `DOMAIN\username` | **PII** | High |
| `path` | `/vol/data/file.docx` | **Sensitive** | Medium |
| `operation` | `create` | Non-sensitive | None |
| `client_ip` | `10.0.x.x` | Internal | Low |

## Data Handling Patterns

### Pattern 1: Full Fidelity (Default)

Ship all fields as-is. Appropriate when:
- Observability platform has access controls (RBAC)
- Data residency requirements are met (same region)
- Security team has approved the data flow
- Retention policies are configured

### Pattern 2: Pseudonymization

Hash PII fields before shipping. Use when:
- Operational visibility needed without identifying individuals
- Cross-border data transfer concerns
- Shared dashboards with broad access

```python
import hashlib

def pseudonymize_user(username: str, salt: str) -> str:
    """One-way hash for user identification without revealing identity."""
    return hashlib.sha256(f"{salt}:{username}".encode()).hexdigest()[:16]

# Result: "admin@corp.local" -> "a3f2b1c9d4e5f678"
```

### Pattern 3: Redaction

Remove sensitive fields entirely. Use when:
- Strict data minimization requirements
- Public or shared observability environments
- Compliance mandates field removal

Implementation via OTel Collector (Part 5):
```yaml
processors:
  attributes:
    actions:
      - key: user.name
        action: delete
      - key: fsxn.path
        action: hash
```

### Pattern 4: Path Generalization

Reduce path specificity while maintaining operational value:

```python
def generalize_path(path: str, depth: int = 3) -> str:
    """Keep only top N path segments."""
    parts = path.split("/")
    if len(parts) > depth + 1:
        return "/".join(parts[:depth + 1]) + "/..."
    return path

# "/vol/hr/employee-records/salary.xlsx" -> "/vol/hr/employee-records/..."
```

## Regulatory Considerations

| Regulation | Key Requirement | Impact on Pipeline |
|-----------|----------------|-------------------|
| **APPI** (Japan) | Personal information handling, cross-border transfer | Evaluate UserName as personal info; prefer JP-region vendors |
| **GDPR** (EU) | Data minimization, right to erasure | Consider pseudonymization; document retention |
| **FISC** (Japan Financial) | Data residency, access control | Ensure vendor data stays in approved regions |
| **ISMAP** (Japan Gov Cloud) | Security controls, audit trail | Full fidelity with access controls |
| **HIPAA** (US Healthcare) | PHI protection | Redact if file paths contain patient identifiers |

> **Governance caveat**: This table provides technical awareness, not legal guidance. Consult your compliance team for binding regulatory interpretation.

## Implementation Recommendations

### For PoC / Validation (Level 1-2)

- Use **Pattern 1 (Full Fidelity)** with sample/synthetic data
- Clearly label test data as non-production
- Restrict observability platform access to PoC team

### For Production (Level 3)

- Implement **Pattern 2 (Pseudonymization)** for UserName in shared dashboards
- Configure vendor-side RBAC (restrict who can see raw logs)
- Set retention policies matching your compliance requirements
- Document the data flow in your data processing register

### For Enterprise / Regulated (Level 4)

- Implement **Pattern 3 (Redaction)** via OTel Collector processors
- Use **Pattern 4 (Path Generalization)** for cross-team dashboards
- Maintain full-fidelity logs in a restricted index/dataset for security investigations
- Implement audit trail for who accessed the observability data

## OTel Collector Redaction Configuration

For the OTel Collector path (Part 5), add redaction processors:

```yaml
processors:
  # Pseudonymize user fields
  transform:
    log_statements:
      - context: log
        statements:
          - set(attributes["user.name.hash"], SHA256(attributes["user.name"]))

  # Remove raw PII after hashing
  attributes/redact:
    actions:
      - key: user.name
        action: delete
      - key: source.ip
        action: delete

  # Generalize file paths
  transform/paths:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/...")
```

## Vendor-Specific Data Controls

| Vendor | RBAC | Field-Level Masking | Retention Control | Data Residency |
|--------|------|--------------------|--------------------|----------------|
| Datadog | Yes | Yes (Sensitive Data Scanner) | Yes | US, EU |
| Grafana Cloud | Yes | No (use Collector) | Yes | US, EU, AU |
| Splunk | Yes | Yes (field masking) | Yes | Self-hosted option |
| Elastic | Yes | Yes (field-level security) | Yes (ILM) | Self-hosted option |
| New Relic | Yes | Yes (obfuscation rules) | Yes | US, EU |
| Honeycomb | Yes | No (use Collector) | Yes | US only |
| Dynatrace | Yes | Yes (data masking) | Yes | Region-specific |
| Sumo Logic | Yes | Yes (field extraction rules) | Yes | JP, US, EU, AU |

## Related Documents

- [Governance & Compliance](governance-and-compliance.md)
- [Security Review Checklist](security-review-checklist.md)
- [Data Residency Matrix](data-residency.md)
- [Pipeline SLO](pipeline-slo.md)
- [OTel Collector Integration](../../integrations/otel-collector/README.md) — Redaction via processors
