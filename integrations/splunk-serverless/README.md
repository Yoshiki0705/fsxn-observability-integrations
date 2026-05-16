# FSxN Splunk Serverless Integration

🚧 **Status: Planned**

## Architecture

```
Pattern A: FSx ONTAP → S3 Access Point → EventBridge → Lambda → Splunk HEC
Pattern B: FSx ONTAP → S3 Access Point → Lambda → Kinesis Data Firehose → Splunk HEC
```

## Background

Existing AWS Blog uses EC2-based approach (syslog-ng + Universal Forwarder).
This integration provides a fully serverless alternative using HTTP Event Collector (HEC).

## API Endpoint

- `https://<splunk-instance>:8088/services/collector/event`

## Authentication

- HEC Token (Header: `Authorization: Splunk <token>`)

## Batch Limits

- No hard limit (recommended chunking for reliability)

## Firehose Support

✅ Built-in Splunk destination in Kinesis Data Firehose
