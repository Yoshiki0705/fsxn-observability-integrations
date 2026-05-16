# FSxN New Relic Integration

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → New Relic Log API
```

## API Endpoint

- US: `https://log-api.newrelic.com/log/v1`
- EU: `https://log-api.eu.newrelic.com/log/v1`

## Authentication

- License Key (Header: `Api-Key`)

## Batch Limits

- Max 1MB per request
