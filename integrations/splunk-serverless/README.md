# FSx for ONTAP Splunk Serverless Integration

🌐 [日本語](docs/ja/setup-guide.md) | [English](docs/en/setup-guide.md)

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

## Overview

Serverless alternative to the [EC2-based Splunk integration](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/) that uses syslog-ng + Universal Forwarder on EC2 instances.

This integration ships FSx ONTAP audit logs directly to Splunk via HTTP Event Collector (HEC), eliminating the need for EC2 instances.

**PoC time estimate**: ~30 minutes from deploy to first queryable event in Splunk (assumes HEC is already configured).

## Architecture Comparison

```
[Existing: EC2-based]
FSx ONTAP → syslog-ng (EC2) → Splunk UF (EC2) → Splunk Enterprise

[This project: Serverless]
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Splunk HEC
```

### Alternative: Firehose Path (High Volume)

For sustained high-volume logs (>1000 events/sec), use Kinesis Data Firehose with its built-in Splunk destination:

```
FSx ONTAP → S3 AP → Lambda (transform) → Kinesis Data Firehose → Splunk HEC
```

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-splunk-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    SplunkHecTokenSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk-hec-token \
    SplunkHecEndpoint=https://splunk.example.com:8088 \
    S3BucketName=my-fsxn-audit-bucket \
    SplunkIndex=fsxn_audit \
  --capabilities CAPABILITY_IAM
```

## Splunk HEC Configuration

### Create HEC Token in Splunk

1. Splunk Web → **Settings** → **Data Inputs** → **HTTP Event Collector**
2. Click **New Token**
3. Configure:
   - Name: `fsxn-audit-log-shipper`
   - Source type: `fsxn:ontap:audit`
   - Index: `fsxn_audit`
4. Copy the generated token

### Store Token in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name "splunk/fsxn-hec-token" \
  --secret-string '{"hec_token":"YOUR_HEC_TOKEN"}' \
  --region ap-northeast-1
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `SplunkHecEndpoint` | ✅ | - | HEC URL (e.g., `https://splunk:8088`) |
| `SplunkHecTokenSecretArn` | ✅ | - | Secrets Manager ARN for HEC token |
| `SplunkIndex` | ❌ | `fsxn_audit` | Target Splunk index |
| `SplunkSourcetype` | ❌ | `fsxn:ontap:audit` | Splunk sourcetype |
| `VerifySSL` | ❌ | `true` | Set `false` for self-signed certs |

## HEC Event Format

```json
{
  "time": 1705315200,
  "host": "svm-prod-01",
  "source": "fsxn-observability",
  "sourcetype": "fsxn:ontap:audit",
  "index": "fsxn_audit",
  "event": {
    "event_type": "4663",
    "user": "admin@corp.local",
    "operation": "ReadData",
    "path": "/vol/data/file.txt",
    "result": "Success"
  }
}
```

## Network Considerations

- Lambda must be able to reach the Splunk HEC endpoint
- If Splunk is in a private VPC, deploy Lambda in the same VPC with NAT Gateway
- For Splunk Cloud, ensure the HEC endpoint is publicly accessible or use AWS PrivateLink

## Query Examples (SPL)

```spl
# Find all failed access attempts
index=fsxn_audit sourcetype=fsxn:ontap:audit result=Failure
| stats count by user, path

# Top operations by volume
index=fsxn_audit sourcetype=fsxn:ontap:audit
| stats count by operation
| sort -count

# Access timeline
index=fsxn_audit sourcetype=fsxn:ontap:audit
| timechart span=5m count by operation

# Specific user investigation
index=fsxn_audit sourcetype=fsxn:ontap:audit user="admin@corp.local"
| table _time, operation, path, result, client_ip
```

## Monitoring

- **CloudWatch Alarm**: Lambda errors > 5 in 10 minutes
- **Dead Letter Queue**: Failed events preserved for 14 days (KMS encrypted)
- **Splunk**: Monitor HEC token health via `_internal` index

## Limits & Known Issues

- No hard batch size limit for HEC, but recommended < 1MB per event
- `VerifySSL=false` disables TLS verification (⚠️ do NOT use in production)
- Splunk Cloud HEC endpoints require allowlisting of Lambda's outbound IP (NAT Gateway EIP)
- For sustained >1000 events/sec, use the Firehose path (`template-firehose.yaml`)

## Cost Estimate

| Monthly Log Volume | AWS Lambda Cost | Splunk License Impact |
|-------------------|----------------|----------------------|
| 1 GB | ~$0.50 | Minimal (within most license allocations) |
| 10 GB | ~$5 | Check daily indexing volume limit |
| 100 GB | ~$50 | Significant — consider Firehose path |

> Splunk pricing is license-based (daily indexing volume). This integration does not change your Splunk license cost — it only changes the delivery mechanism from EC2 to Lambda.

## Related Documents

- [Vendor Comparison](../../docs/en/vendor-comparison.md)
- [PoC Success Criteria](../../docs/en/poc-success-criteria.md)
