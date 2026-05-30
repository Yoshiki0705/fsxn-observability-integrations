# FSx for ONTAP Grafana Cloud Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Architecture

```
FSx for ONTAP → S3 Access Point → EventBridge → Lambda → Grafana Cloud OTLP Gateway
                                                      (fallback: Loki Push API)
```

> **Note**: The recommended path is via the OTLP Gateway (`https://otlp-gateway-prod-<region>.grafana.net/otlp`), NOT the Loki Push API directly. The `otlp_http` exporter is verified working; the `loki` exporter is a legacy fallback only.

**PoC time estimate**: ~30 minutes from deploy to first queryable log in Grafana Cloud.

## Direct OTLP vs OTel Collector — Decision Guide

| Criteria | Direct (this integration) | Via OTel Collector |
|----------|--------------------------|-------------------|
| **Simplicity** | ✅ Fewer moving parts | ❌ Collector infra required |
| **Single backend (Grafana only)** | ✅ Recommended | Overkill |
| **Multi-backend (Grafana + others)** | ❌ Separate Lambda per vendor | ✅ Single Lambda, fan-out in Collector |
| **Redaction / PII filtering** | ❌ Must implement in Lambda | ✅ Collector processors handle it |
| **Routing rules** | ❌ Not supported | ✅ Route by severity, SVM, etc. |
| **Cost (Grafana only)** | ✅ Lower (no Collector) | Higher (+$9-36/month for Fargate) |

**Recommendation**:
- Grafana Cloud as your **only** backend → Use this integration (Direct OTLP)
- Grafana Cloud + other backends → Use [OTel Collector integration](../otel-collector/)
- Need redaction or routing → Use [OTel Collector integration](../otel-collector/)

## ONTAP-Side Prerequisites

Before deploying this integration, ensure:

- Audit logging enabled on the target SVM (`vserver audit create`)
- Audit policy covers required SMB/NFS events
- Audit log format is known (EVTX or XML/JSON-converted output)
- Audit log rotation interval is documented
- Audit log path exposed through an FSx for ONTAP S3 Access Point
- S3 Access Point file-system identity has read permission on the audit log directory
- Test audit file is visible through the S3 Access Point (`aws s3 ls` on AP ARN)
- EMS webhook destination configured for relevant events (if using EMS path)
- FPolicy server deployed and reachable from ONTAP (if using file-operation stream path)

See [Prerequisites Guide](../../docs/en/prerequisites.md) for detailed setup instructions.

## Grafana Cloud Setup Checklist

Before deploying, gather these from your Grafana Cloud console:

- [ ] Create a Grafana Cloud stack (or use existing)
- [ ] Locate OTLP endpoint: `https://otlp-gateway-prod-<region>.grafana.net/otlp`
- [ ] Create a `logs:write` scoped API token for OTLP ingestion
- [ ] Create a Grafana Service Account token for dashboard/alert provisioning (separate from ingestion token)
- [ ] Store ingestion credentials in AWS Secrets Manager as `{"instance_id":"<id>","api_key":"<token>"}`
- [ ] Store dashboard provisioning token separately (used by `create-dashboard.sh` and `create-alerts.sh`)

Use separate credentials for each concern:
- **OTLP ingestion**: `logs:write` scoped token (stored in Secrets Manager, used by Lambda)
- **Grafana HTTP API provisioning**: dashboard / alert provisioning permissions (used by scripts only)

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-grafana-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    GrafanaCredentialsSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:grafana-creds \
    LokiEndpoint=https://logs-prod-us-central1.grafana.net \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Authentication

Basic Auth with Grafana Cloud Instance ID and API Key:

```bash
aws secretsmanager create-secret \
  --name "grafana/fsxn-credentials" \
  --secret-string '{"instance_id":"123456","api_key":"glc_xxx..."}' \
  --region ap-northeast-1
```

## Loki Labels

Each log stream is labeled with:
- `job=fsxn-audit`
- `source=fsxn-ontap`
- `svm=<svm-name>`
- `s3_key=<object-key>`

## LogQL Query Examples

```logql
{job="fsxn-audit"} | json | operation="ReadData"
{job="fsxn-audit", svm="svm-prod-01"} | json | Result="Failure"
{job="fsxn-audit"} | json | line_format "{{.UserName}} {{.Operation}} {{.ObjectName}}"
```

## Monitoring

- **CloudWatch Alarm**: Lambda errors > 5 in 10 minutes
- **Dead Letter Queue**: Failed events preserved for 14 days (KMS encrypted)
- **Grafana Cloud**: Monitor ingestion rate via Cloud Portal usage dashboard

## Limits & Known Issues

- Use `otlp_http` exporter (NOT `loki` exporter) for OTLP Gateway
- Basic Auth value must be `base64(instanceId:apiToken)` — NOT plain text
- Grafana Cloud Free Tier: 50 GB/month logs, 14-day retention
- No Firehose support — Lambda direct delivery only
- **Data residency**: Grafana Cloud stacks are region-specific (US, EU, AP). Select the stack region matching your data residency requirements. Evaluate cross-border data transfer with your compliance team.

## Cost Estimate

| Monthly Log Volume | Grafana Cloud Cost | Notes |
|-------------------|-------------------|-------|
| 1 GB | $0 | Free tier (50 GB/month) |
| 10 GB | $0 | Free tier |
| 50 GB | $0 | At free tier limit |
| 100 GB | ~$25 | $0.50/GB beyond 50 GB free |

> Grafana Cloud Free Tier includes 50 GB/month of log ingestion with 14-day retention. Pro tier extends retention to 30 days.

## Related Documents

- [OTel Collector Integration](../otel-collector/) — Multi-backend via Collector (verified with Grafana)
- [Vendor Comparison](../../docs/en/vendor-comparison.md)
- [PoC Success Criteria](../../docs/en/poc-success-criteria.md)
