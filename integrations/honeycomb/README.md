# FSxN Honeycomb Integration

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Honeycomb Events API
```

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-honeycomb-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    HoneycombApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:honeycomb-key \
    HoneycombDataset=fsxn-audit \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Authentication

- API Key (Header: `X-Honeycomb-Team: <key>`)

## Batch API Format

```json
[
  {
    "time": "2026-01-15T12:00:00Z",
    "data": {
      "source": "fsxn-ontap",
      "event_type": "4663",
      "user": "admin@corp.local",
      "operation": "ReadData",
      "path": "/vol/data/file.txt",
      "result": "Success",
      "svm": "svm-prod-01"
    }
  }
]
```

## Limits

- Max 100 events per batch request
- Max 5MB per request
- Endpoint: `https://api.honeycomb.io/1/batch/<dataset>`
