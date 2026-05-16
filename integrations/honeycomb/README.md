# FSxN Honeycomb Integration

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Honeycomb Events API
```

## API Endpoint

- `https://api.honeycomb.io/1/batch/<dataset>`

## Authentication

- API Key (Header: `X-Honeycomb-Team`)

## Batch Limits

- Max 5MB per request
