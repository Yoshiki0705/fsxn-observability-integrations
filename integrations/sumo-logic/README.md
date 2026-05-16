# FSxN Sumo Logic Integration

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → Sumo Logic HTTP Source
```

## API Endpoint

- `https://endpoint<N>.collection.sumologic.com/receiver/v1/http/<token>`

## Authentication

- Embedded in URL (HTTP Source endpoint)

## Batch Limits

- Max 1MB per request
