# Security Review Checklist

🌐 [日本語](../ja/security-review-checklist.md) | **English** (this page)

This checklist supports security teams reviewing the FSx for ONTAP observability pipeline before deployment in production or regulated environments.

## IAM Roles and Permissions

- [ ] Lambda execution role uses least-privilege permissions
- [ ] S3 Access Point List/GetObject resources are scoped to specific AP ARN
- [ ] Secrets Manager access is scoped to the specific secret ARN (not `*`)
- [ ] SSM Parameter Store access is scoped to the checkpoint parameter path
- [ ] SQS DLQ permissions are scoped to the specific queue ARN
- [ ] No IAM policies use `Resource: "*"` for data-plane actions
- [ ] CloudWatch Logs permissions are scoped to the function's log group
- [ ] EventBridge Scheduler role can only invoke the specific Lambda function

## Secrets Management

- [ ] No API token or key is stored in CloudFormation parameters as plaintext
- [ ] Ingestion token (vendor API key) and provisioning credentials are separated
- [ ] Secrets Manager secret has a defined rotation schedule
- [ ] Lambda handles 401/403 from vendor by logging error (not exposing token)
- [ ] Token cache invalidation is tested (cold start refresh behavior)
- [ ] `NoEcho: true` is set on any sensitive CloudFormation parameters

## Network Security

- [ ] Lambda VPC placement decision is documented and justified
  - VPC-external: for S3 AP read-only functions (simplest, no NAT cost)
  - VPC-internal + NAT: for functions needing both S3 AP and ONTAP REST API
- [ ] API Gateway webhook endpoint is not publicly unauthenticated in production
- [ ] Source IP restriction, IAM auth, Lambda authorizer, or WAF is configured for webhooks
- [ ] Security Groups for ECS Fargate (FPolicy) allow only TCP:9898 from ONTAP IPs
- [ ] No overly permissive egress rules (0.0.0.0/0) without justification

## Data Protection

- [ ] Audit logs are encrypted at rest (SSE-FSx on the volume)
- [ ] Data in transit uses TLS (HTTPS to vendor endpoints)
- [ ] DLQ messages do not contain full audit log payloads (or retention is limited)
- [ ] CloudWatch Logs encryption is configured (KMS CMK if required)
- [ ] No PII is logged in Lambda function logs beyond what's in the audit events

## CloudFormation Template Security

- [ ] Templates pass `cfn-lint` validation without errors
- [ ] Templates pass `cfn-guard` policy rules (if configured)
- [ ] No hardcoded credentials, account IDs, or resource IDs in templates
- [ ] Parameters use `AllowedPattern` constraints where applicable
- [ ] `DeletionPolicy: Retain` is set on critical resources (logs, DLQ)
- [ ] Stack termination protection is recommended for production

## Operational Security

- [ ] CloudWatch Alarms are configured for:
  - Lambda errors (Errors metric > 0)
  - DLQ message count (ApproximateNumberOfMessages > 0)
  - Checkpoint staleness (custom metric or alarm on scheduler failures)
- [ ] Log retention is explicitly configured (not indefinite)
- [ ] DLQ alarm triggers notification to operations team
- [ ] Deployment changes require pull request review

## Vendor Destination Security

- [ ] SaaS destination is approved by security/compliance team
- [ ] Data residency requirements are met (destination region)
- [ ] Vendor's security certifications are reviewed (SOC 2, ISO 27001)
- [ ] Data processing agreement (DPA) is in place with vendor
- [ ] Vendor API endpoint uses TLS 1.2+
- [ ] Rate limiting and backoff are implemented to prevent credential exposure on retry storms

## Incident Response

- [ ] Delivery failure escalation path is defined
- [ ] DLQ replay procedure is documented and approved
- [ ] Token compromise response procedure exists (rotate + redeploy)
- [ ] Monitoring covers both pipeline health and security events

## Related Documents

- [Governance and Compliance](governance-and-compliance.md)
- [Delivery Guarantee Patterns](delivery-guarantees.md)
- [Webhook Security Guide](webhook-security.md)
- [Operational Guide](operational-guide.md)
