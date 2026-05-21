# FSx for ONTAP Dynatrace Integration

> 📖 **Shared docs**: [Delivery Guarantee Patterns](../../docs/en/delivery-guarantees.md) | [Webhook Security](../../docs/en/webhook-security.md)

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Dynatrace Log Ingest API
```

## API Endpoint

- `https://<environment-id>.live.dynatrace.com/api/v2/logs/ingest`

## Authentication

- API Token (Header: `Authorization: Api-Token <token>`)

## Batch Limits

- Max 1MB per request
