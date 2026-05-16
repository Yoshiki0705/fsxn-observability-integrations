# FSxN OpenTelemetry Collector Integration

🚧 **Status: Planned**

## Architecture

```
FSx ONTAP → S3 Access Point → EventBridge → Lambda → OTLP/HTTP Endpoint
```

## Overview

Vendor-neutral integration using OpenTelemetry Protocol (OTLP).
Can forward to any OTLP-compatible backend.

## API Endpoint

- `http://<collector>:4318/v1/logs` (OTLP/HTTP)
- `http://<collector>:4317` (OTLP/gRPC)

## Authentication

- Configurable (depends on collector setup)

## Benefits

- Vendor-neutral: switch backends without code changes
- Standard format: OTLP log data model
- Flexible routing: collector can fan-out to multiple backends
