# FSxN Elastic Integration

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Elasticsearch Bulk API
```

## API Endpoint

- `https://<cluster>.es.<region>.aws.found.io:9243/_bulk`

## Authentication

- API Key or Basic Auth

## Batch Limits

- Recommended 10MB per request
