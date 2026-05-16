# FSx for ONTAP Sumo Logic Integration

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Sumo Logic HTTP Source
```

## Authentication

Sumo Logic uses HTTP Source URLs with embedded authentication tokens. Store the full URL in Secrets Manager.

```bash
aws secretsmanager create-secret \
  --name "sumo-logic/fsxn-http-source" \
  --secret-string '{"url":"https://endpoint1.collection.sumologic.com/receiver/v1/http/TOKEN"}' \
  --region ap-northeast-1
```

## Limits

- Max 1MB per request
- Newline-delimited JSON format
- Custom metadata via `X-Sumo-*` headers

## Sumo Logic Headers

- `X-Sumo-Category`: `aws/fsxn/audit`
- `X-Sumo-Name`: `fsxn-ontap-audit`
- `X-Sumo-Host`: `fsxn-ontap`
