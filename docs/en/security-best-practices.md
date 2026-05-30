# Security Best Practices for FSxN Observability Integrations

## Overview

This document consolidates security considerations across all vendor integrations. Apply these practices regardless of which observability backend you choose.

## Secrets Management

### Do

- Store all API keys, tokens, and credentials in **AWS Secrets Manager**
- Use IAM policies to restrict which Lambda functions can access which secrets
- Rotate secrets on a regular schedule (quarterly recommended)
- Use separate secrets per integration (don't share a single secret across vendors)

### Don't

- Store secrets in Lambda environment variables (visible in console)
- Hardcode secrets in CloudFormation templates or source code
- Log secret values (even partially) in CloudWatch Logs
- Share secrets across AWS accounts without cross-account IAM policies

### Vendor-Specific Notes

| Vendor | Secret Format | Rotation Method |
|--------|--------------|-----------------|
| Datadog | `{"api_key":"..."}` | Regenerate in Datadog console |
| New Relic | `{"license_key":"..."}` | Regenerate in NR API Keys page |
| Grafana Cloud | `{"instance_id":"...","api_key":"..."}` | Create new token, delete old |
| Splunk | `{"hec_token":"..."}` | Create new HEC token in Splunk |
| Elastic | `{"api_key":"base64_id:key"}` | Invalidate + create new API key |
| Dynatrace | `{"api_token":"dt0c01.XXX.YYY"}` | Revoke + create new token |
| Sumo Logic | `{"url":"https://..."}` | Create new HTTP Source (new URL) |
| Honeycomb | `{"api_key":"hcaik_..."}` | Regenerate ingest key |

## Network Security

### Lambda Placement Decision

| Scenario | Recommendation | Why |
|----------|---------------|-----|
| S3 AP read only | Lambda outside VPC | Simplest, no NAT cost |
| S3 AP + ONTAP REST | Lambda in VPC + NAT | Both paths need internet |
| Vendor in private network | Lambda in VPC + VPC peering | Direct connectivity |

### TLS Requirements

- All vendor API calls use HTTPS (TLS 1.2+)
- Never set `VerifySSL=false` in production
- For self-signed certificates (dev only), use a custom CA bundle instead

### Firewall / Security Group Rules

If Lambda is in a VPC:
- Outbound: Allow HTTPS (443) to vendor endpoints
- Outbound: Allow HTTPS (443) to Secrets Manager endpoint
- No inbound rules needed for Lambda

## IAM Least Privilege

### Lambda Execution Role Pattern

```yaml
# Minimum permissions for audit log shipper
Policies:
  - PolicyName: S3Read
    PolicyDocument:
      Statement:
        - Effect: Allow
          Action: s3:GetObject
          Resource: !Sub '${S3AccessPointArn}/object/*'  # Scoped to AP
  - PolicyName: Secrets
    PolicyDocument:
      Statement:
        - Effect: Allow
          Action: secretsmanager:GetSecretValue
          Resource: !Ref ApiKeySecretArn  # Single secret only
  - PolicyName: DLQ
    PolicyDocument:
      Statement:
        - Effect: Allow
          Action: sqs:SendMessage
          Resource: !GetAtt DeadLetterQueue.Arn  # Specific queue only
```

### Anti-Patterns

- `Resource: "*"` on any action
- `secretsmanager:*` instead of `secretsmanager:GetSecretValue`
- `s3:*` instead of `s3:GetObject`
- Sharing execution roles across multiple Lambda functions

## Dead Letter Queue Security

- DLQ messages may contain audit log data (file paths, usernames, IPs)
- Enable KMS encryption on all DLQ queues (`KmsMasterKeyId: alias/aws/sqs`)
- Set message retention to 14 days (enough for replay, not indefinite)
- Restrict DLQ access to the Lambda role and ops team only

## Webhook Security (EMS Path)

The EMS webhook path exposes an API Gateway endpoint. Secure it:

1. **API Key**: Require `x-api-key` header on all requests
2. **WAF**: Attach AWS WAF with rate limiting (100 req/min recommended)
3. **IP Allowlist**: Restrict to FSx for ONTAP management IP range
4. **Request Validation**: Validate EMS event schema before processing

See [Webhook Security Guide](webhook-security.md) for detailed configuration.

## Audit Log Data Classification

FSx for ONTAP audit logs may contain:

| Data Type | Example | Sensitivity |
|-----------|---------|-------------|
| Usernames | `admin@corp.local` | PII (depending on jurisdiction) |
| File paths | `/vol/hr/salary-2026.xlsx` | Business confidential |
| Client IPs | `10.0.x.x` | Internal network topology |
| SVM names | `svm-prod-finance` | Infrastructure metadata |

### Recommendations

- Apply PII redaction in the OTel Collector if sending to external vendors
- Use the `transform` processor to mask usernames or file paths
- Consider data residency requirements when choosing vendor regions
- Document which data fields are sent to which vendors

## Compliance Considerations

> This section provides technical guidance only. It does not constitute legal, compliance, or regulatory advice. Consult your compliance team for authoritative guidance.

| Framework | Relevant Controls | This Project Helps With |
|-----------|------------------|------------------------|
| SOC 2 | CC6.1 (Logical access) | File access audit trail |
| HIPAA | 164.312(b) (Audit controls) | Access logging for PHI volumes |
| PCI DSS | 10.2 (Audit trail) | Cardholder data access monitoring |
| GDPR | Art. 30 (Records of processing) | Data access documentation |

### What This Project Does NOT Provide

- Compliance certification or attestation
- Legal interpretation of regulatory requirements
- Guaranteed completeness of audit coverage
- Tamper-proof log storage (use S3 Object Lock for that)

## Pre-Deployment Security Checklist

- [ ] Secrets stored in Secrets Manager (not env vars)
- [ ] IAM roles follow least privilege
- [ ] DLQ encrypted with KMS
- [ ] TLS verification enabled (no `VerifySSL=false`)
- [ ] Webhook endpoint secured (API key + WAF)
- [ ] No real credentials in source code or templates
- [ ] Data classification reviewed for chosen vendor
- [ ] Secrets rotation schedule documented
- [ ] DLQ replay procedure approved by security team
- [ ] Cross-border data transfer reviewed (if applicable)
