# EMS Webhook → Grafana Cloud Loki Setup

🌐 [日本語](../ja/ems-webhook-setup.md) | **English** (this page)

## Overview

Configuration procedure for forwarding ONTAP EMS (Event Management System) events to Grafana Cloud Loki via API Gateway.

## Architecture

```
ONTAP EMS → HTTPS Webhook → API Gateway (REST) → Lambda → Grafana Cloud OTLP Gateway
```

## Prerequisites

- FSx for ONTAP file system running
- Grafana Cloud account (Loki enabled)
- Credentials registered in AWS Secrets Manager

## Step 1: Infrastructure Deployment

### 1.1 Deploy EMS Lambda Stack

```bash
aws cloudformation deploy \
  --template-file integrations/grafana/template-ems.yaml \
  --stack-name fsxn-grafana-ems \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    GrafanaCredentialsSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:grafana/fsxn-loki-credentials-XXXXXX \
    LokiEndpoint=https://otlp-gateway-prod-ap-northeast-0.grafana.net/otlp \
    EmsParserLayerArn=arn:aws:lambda:ap-northeast-1:123456789012:layer:fsxn-ems-parser:1 \
  --region ap-northeast-1
```

### 1.2 Deploy API Gateway Stack

```bash
# Get Lambda ARN from stack outputs
LAMBDA_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-grafana-ems \
  --query "Stacks[0].Outputs[?OutputKey=='EmsHandlerFunctionArn'].OutputValue" \
  --output text --region ap-northeast-1)

# Deploy API Gateway stack
aws cloudformation deploy \
  --template-file shared/templates/ems-webhook-apigw.yaml \
  --stack-name fsxn-grafana-ems-webhook \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides LambdaFunctionArn=$LAMBDA_ARN \
  --region ap-northeast-1
```

### 1.3 Retrieve API Gateway Endpoint URL

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-grafana-ems-webhook \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpointUrl'].OutputValue" \
  --output text --region ap-northeast-1
```

Example output: `https://<api-id>.execute-api.ap-northeast-1.amazonaws.com/prod/ems`

## Step 2: ONTAP EMS Webhook Configuration

> **Note**: The following commands are executed on the ONTAP CLI (SSH or System Manager CLI).

### 2.1 Create EMS Webhook Destination

```
event notification destination create -name grafana-webhook \
  -rest-api-url https://<api-id>.execute-api.ap-northeast-1.amazonaws.com/prod/ems
```

### 2.2 Create EMS Notification

Create a notification using the important events filter:

```
event notification create -filter-name important-events \
  -destinations grafana-webhook
```

### 2.3 Create Custom Filters (Optional)

To forward only specific events:

```
# ARP (Anti-Ransomware Protection) events only
event filter create -filter-name arp-events
event filter rule add -filter-name arp-events \
  -type include \
  -message-name arw.*

event notification create -filter-name arp-events \
  -destinations grafana-webhook
```

```
# Quota exceeded events only
event filter create -filter-name quota-events
event filter rule add -filter-name quota-events \
  -type include \
  -message-name wafl.quota.*

event notification create -filter-name quota-events \
  -destinations grafana-webhook
```

### 2.4 Verify Configuration

```
event notification show
event notification destination show -name grafana-webhook
```

## Step 3: Verification

### 3.1 Send Test Event (curl)

```bash
curl -X POST https://<api-id>.execute-api.ap-northeast-1.amazonaws.com/prod/ems \
  -H "Content-Type: application/json" \
  -d '{
    "messageName": "arw.volume.state",
    "severity": "alert",
    "time": "2026-01-15T10:00:00Z",
    "node": "fsxn-node-01",
    "svmName": "svm-prod-01",
    "message": "Anti-ransomware: Volume vol1 state changed to attack-detected",
    "parameters": {
      "volume_name": "vol1",
      "state": "attack-detected",
      "vserver": "svm-prod-01"
    }
  }'
```

Expected response:
```json
{"status": "ok", "event_name": "arw.volume.state", "delivered": true}
```

### 3.2 Verify in Grafana Explore

Grafana Cloud → Explore → Loki data source:

```
{service_name="fsxn-ems"}
```

> **Note**: When using the OTLP Gateway, the label is `service_name`.

### 3.3 Filter by Severity

```
{service_name="fsxn-ems"} | json | severity="alert"
```

## Troubleshooting

### EMS Events Not Arriving

1. **Check Lambda CloudWatch Logs**:
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/fsxn-grafana-ems-ems-handler \
     --filter-pattern "ERROR" \
     --region ap-northeast-1
   ```

2. **Check API Gateway access logs**:
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/apigateway/fsxn-grafana-ems-webhook-ems-access \
     --region ap-northeast-1
   ```

3. **Check ONTAP side**:
   ```
   event notification destination show -name grafana-webhook
   event log show -messagename arw.*
   ```

### Authentication Errors (401/403)

- Verify Secrets Manager credentials:
  ```bash
  aws secretsmanager get-secret-value \
    --secret-id grafana/fsxn-loki-credentials \
    --query "SecretString" --output text --region ap-northeast-1
  ```
- Verify Instance ID and API Key are correct
- Verify API Key has `logs:write` scope

## Label Design

| Label | Value | Description |
|-------|-------|-------------|
| `service_name` | `fsxn-ems` | OTLP resource attribute (service.name) |
| `source` | `ontap` | Source system |
| `severity` | `alert`, `warning`, etc. | EMS severity level (log attribute) |
