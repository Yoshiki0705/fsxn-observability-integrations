# FSx for ONTAP Grafana Cloud Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Grafana Loki Push API
```

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
