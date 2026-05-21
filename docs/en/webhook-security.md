# EMS Webhook Security Guide

## Overview

ONTAP EMS webhooks deliver event notifications to an HTTPS endpoint. This guide covers securing the API Gateway endpoint that receives those events.

## Authentication Modes

The shared EMS webhook template (`shared/templates/ems-webhook-apigw.yaml`) supports four authentication modes:

| Mode | `WebhookAuthMode` | Use Case | ONTAP Compatibility |
|------|-------------------|----------|---------------------|
| None | `NONE` | Quickstart / PoC only | ✅ No config needed |
| API Key | `API_KEY` | Basic protection with usage plans | ✅ Custom header support |
| IAM SigV4 | `IAM` | AWS-native auth | ⚠️ Requires SigV4 signing capability |
| Shared Secret | `SHARED_SECRET` | Production recommended | ✅ Bearer token in Authorization header |

## Recommended: Shared Secret (Lambda Authorizer)

For production EMS webhooks, use `SHARED_SECRET` mode. This deploys a Lambda authorizer that validates a Bearer token against a secret stored in Secrets Manager.

### How It Works

```
ONTAP EMS → HTTPS POST with Authorization: Bearer <token>
    → API Gateway
    → Lambda Authorizer (validates token against Secrets Manager)
    → If valid: invoke EMS handler Lambda
    → If invalid: return 401/403
```

### Setup

1. **Create the webhook secret in Secrets Manager**:

```bash
aws secretsmanager create-secret \
  --name "fsxn/ems-webhook-secret" \
  --secret-string '{"webhook_secret": "<generate-a-strong-random-token>"}' \
  --region ap-northeast-1
```

2. **Deploy with SHARED_SECRET mode**:

```bash
aws cloudformation deploy \
  --template-file shared/templates/ems-webhook-apigw.yaml \
  --stack-name fsxn-ems-webhook \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    LambdaFunctionArn=<ems-handler-arn> \
    WebhookAuthMode=SHARED_SECRET \
    WebhookSecretArn=<secret-arn>
```

3. **Configure ONTAP EMS webhook destination** with the Authorization header:

```
vserver ems destination create -name grafana-webhook \
  -rest-api-url https://<api-id>.execute-api.<region>.amazonaws.com/prod/ems \
  -certificate-authority <ca-name>
```

> **Note**: ONTAP EMS webhook configuration for custom headers varies by ONTAP version. Consult your ONTAP documentation for the correct syntax to add an `Authorization: Bearer <token>` header to webhook requests.

### Secret Rotation

The Lambda authorizer caches the secret for 5 minutes (configurable via `_SECRET_TTL` in the authorizer code). After rotating the secret in Secrets Manager:

1. Both old and new tokens will work during the cache TTL window
2. After 5 minutes, only the new token is accepted
3. No Lambda redeployment required

For zero-downtime rotation:
1. Update the secret with the new token
2. Wait for authorizer cache to expire (5 min)
3. Update ONTAP EMS webhook configuration with the new token

## Additional Hardening

Regardless of authentication mode, consider these additional controls:

### API Gateway Resource Policy

Restrict access by source IP or VPC:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": "execute-api:/*",
      "Condition": {
        "IpAddress": {
          "aws:SourceIp": ["<ontap-management-ip>/32"]
        }
      }
    }
  ]
}
```

### WAF Integration

For internet-facing endpoints, attach AWS WAF with:
- Rate limiting (prevent abuse)
- IP reputation lists
- Request size limits
- Geographic restrictions

### Throttling

The template includes configurable throttling:
- `ThrottlingRateLimit`: Requests per second (default: 100)
- `ThrottlingBurstLimit`: Burst capacity (default: 50)

Tune these based on your EMS event volume.

## Security Decision Matrix

| Deployment | Recommended Auth | Additional Controls |
|-----------|-----------------|---------------------|
| Dev/PoC | `NONE` | None needed |
| Staging | `API_KEY` | Throttling |
| Production (private network) | `SHARED_SECRET` | Resource policy (source IP) |
| Production (internet-facing) | `SHARED_SECRET` | Resource policy + WAF + throttling |

## Recommended Production Baseline

For most deployments, the following combination provides strong security without excessive complexity:

1. **API Gateway Lambda authorizer** with shared secret (Bearer token)
2. **Secret stored in AWS Secrets Manager** with rotation schedule
3. **Source IP restrictions** via API Gateway resource policy (if ONTAP management addresses are stable)
4. **AWS WAF** for internet-facing endpoints (rate limiting, IP reputation)
5. **API Gateway access logging** enabled for audit trail
6. **CloudWatch alarm** on authorization failures (`4XX` count)
7. **Secret rotation runbook** documented and tested

> Start with items 1–3 for initial production deployment. Add WAF (item 4) when the endpoint is internet-facing or when compliance requires it.

## Files

| File | Purpose |
|------|---------|
| `shared/templates/ems-webhook-apigw.yaml` | API Gateway CloudFormation template |
| `shared/lambda/authorizers/shared_secret_authorizer.py` | Lambda authorizer code |
| `shared/python/auth_cache.py` | Reusable credential cache (for handler-side auth) |
