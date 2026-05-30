# OTel Collector PII Redaction Cookbook

## Overview

This cookbook provides ready-to-use OTel Collector processor configurations for redacting, pseudonymizing, or generalizing PII fields in FSx for ONTAP audit logs before they reach your observability backend.

Use this when:
- Shipping logs to a vendor without JP data residency
- Sharing dashboards with teams that should not see usernames
- Complying with data minimization requirements (GDPR, APPI)
- Separating security investigation (full fidelity) from operational monitoring (redacted)

## Prerequisites

- OTel Collector deployed (see the [OTel Collector README](../../README.md))
- Collector version 0.90+ (for `transform` processor support)

## PII Fields in FSx for ONTAP Audit Logs

| Field | Risk Level | Example | Redaction Strategy |
|-------|-----------|---------|-------------------|
| `user.name` / `UserName` | High (PII) | `admin@corp.local` | Hash or delete |
| `fsxn.path` / `ObjectName` | Medium (sensitive) | `/vol/hr/salary.xlsx` | Generalize or hash |
| `source.ip` / `ClientIP` | Low (internal) | `10.0.x.x` | Usually keep; delete if needed |
| `fsxn.svm` | Low (infra) | `svm-prod-01` | Usually keep |

## Recipe 1: Delete PII Fields

Simplest approach — remove fields entirely.

```yaml
processors:
  attributes/delete-pii:
    actions:
      - key: user.name
        action: delete
      - key: UserName
        action: delete
      - key: source.ip
        action: delete
      - key: ClientIP
        action: delete
```

**Trade-off**: Cannot investigate per-user activity. Use when operational monitoring does not require user identification.

## Recipe 2: Hash (Pseudonymize) User Fields

One-way hash preserves cardinality for GROUP BY without revealing identity.

```yaml
processors:
  transform/hash-users:
    log_statements:
      - context: log
        statements:
          - set(attributes["user.name.hash"], SHA256(Concat([attributes["user.name"], "your-salt-here"])))
          - delete_key(attributes, "user.name")
          - set(attributes["UserName.hash"], SHA256(Concat([attributes["UserName"], "your-salt-here"])))
          - delete_key(attributes, "UserName")
```

**Trade-off**: Can still GROUP BY user (hashed), but cannot reverse to real username without the salt. Security team keeps the salt for investigations.

## Recipe 3: Generalize File Paths

Keep top-level directory structure, remove specific filenames.

```yaml
processors:
  transform/generalize-paths:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/***")
          - replace_pattern(attributes["ObjectName"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/***")
```

**Result**: `/vol/hr/employee-records/john-doe-salary-2026.xlsx` becomes `/vol/hr/employee-records/***`

**Trade-off**: Lose specific file identification, but retain directory-level access patterns.

## Recipe 4: Conditional Redaction (Keep for Security, Redact for Ops)

Route full-fidelity logs to a security backend and redacted logs to an ops backend.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  attributes/redact-for-ops:
    actions:
      - key: user.name
        action: delete
      - key: UserName
        action: delete
      - key: source.ip
        action: delete

  transform/generalize-for-ops:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/***")

exporters:
  otlphttp/security:
    endpoint: https://security-backend.example.com
    headers:
      Authorization: "Bearer ${SECURITY_TOKEN}"

  otlphttp/ops:
    endpoint: https://ops-backend.example.com
    headers:
      Authorization: "Bearer ${OPS_TOKEN}"

service:
  pipelines:
    logs/security:
      receivers: [otlp]
      processors: []
      exporters: [otlphttp/security]

    logs/ops:
      receivers: [otlp]
      processors: [attributes/redact-for-ops, transform/generalize-for-ops]
      exporters: [otlphttp/ops]
```

## Recipe 5: APPI-Compliant Configuration (Japan)

For Japanese enterprises under APPI, keep data in JP region and pseudonymize usernames:

```yaml
processors:
  transform/appi:
    log_statements:
      - context: log
        statements:
          - set(attributes["user.hash"], SHA256(Concat([attributes["user.name"], "${HASH_SALT}"])))
          - delete_key(attributes, "user.name")
          - delete_key(attributes, "UserName")

exporters:
  otlphttp/sumo-jp:
    endpoint: https://collectors.jp.sumologic.com/receiver/v1/http/${SUMO_TOKEN}
    headers:
      X-Sumo-Category: aws/fsxn/audit
```

## Recipe 6: GDPR Data Minimization

For EU deployments, minimize data to what is strictly necessary:

```yaml
processors:
  attributes/gdpr-minimize:
    actions:
      - key: user.name
        action: delete
      - key: UserName
        action: delete
      - key: source.ip
        action: delete
      - key: ClientIP
        action: delete

  transform/gdpr-paths:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+)/.*", "$$1/***")
```

## Recipe 7: Sensitive Path Detection and Routing

Route logs containing sensitive paths to a restricted pipeline:

```yaml
processors:
  transform/classify:
    log_statements:
      - context: log
        conditions:
          - IsMatch(attributes["fsxn.path"], ".*(confidential|restricted|hr|finance).*")
        statements:
          - set(attributes["sensitivity"], "high")
      - context: log
        conditions:
          - not IsMatch(attributes["fsxn.path"], ".*(confidential|restricted|hr|finance).*")
        statements:
          - set(attributes["sensitivity"], "normal")
```

## Testing Redaction

Verify your redaction config before production:

```bash
# 1. Start Collector with debug exporter
otelcol --config redaction-test-config.yaml

# 2. Send test log with PII
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d '{
    "resourceLogs": [{
      "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "test"}}]},
      "scopeLogs": [{
        "logRecords": [{
          "body": {"stringValue": "test"},
          "attributes": [
            {"key": "user.name", "value": {"stringValue": "admin@corp.local"}},
            {"key": "fsxn.path", "value": {"stringValue": "/vol/hr/salary/john.xlsx"}}
          ]
        }]
      }]
    }]
  }'

# 3. Check debug output -- user.name should be absent or hashed
```

## Related Documents

- [Data Classification Guide](../../../../docs/en/data-classification.md)
- [Retention Policy Matrix](../../../../docs/en/retention-policy-matrix.md)
- [OTel Collector README](../../README.md)
