# FSxN Grafana Cloud Integration

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Grafana Loki Push API
```

## API Endpoint

- `https://<instance>.grafana.net/loki/api/v1/push`

## Authentication

- Basic Auth (Instance ID + API Key)

## Batch Limits

- Recommended 4MB per request
