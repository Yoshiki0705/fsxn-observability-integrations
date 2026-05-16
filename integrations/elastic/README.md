# FSxN Elastic Integration

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Elasticsearch Bulk API
```

## Quick Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-elastic-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    ElasticApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:elastic-key \
    ElasticEndpoint=https://my-cluster.es.ap-northeast-1.aws.found.io:9243 \
    S3BucketName=my-fsxn-audit-bucket \
  --capabilities CAPABILITY_IAM
```

## Authentication

- API Key (Header: `Authorization: ApiKey <encoded-key>`)
- Alternatively: Basic Auth

## Index Pattern

- Daily indices: `fsxn-audit-YYYY.MM.DD`
- ECS-compatible field mapping

## Document Format (ECS)

```json
{
  "@timestamp": "2026-01-15T12:00:00Z",
  "event": {"type": "4663"},
  "user": {"name": "admin@corp.local"},
  "source": {"ip": "10.0.1.50"},
  "fsxn": {"operation": "ReadData", "path": "/vol/data/file.txt", "result": "Success", "svm": "svm-01"},
  "cloud": {"provider": "aws", "service": {"name": "fsx-ontap"}}
}
```
