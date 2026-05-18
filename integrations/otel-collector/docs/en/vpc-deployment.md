# VPC Deployment Guide — OTel Collector on ECS Fargate

This document describes deploying the OTel Collector on ECS Fargate within a VPC, enabling Lambda functions to forward logs to external backends through a centralized collector.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ VPC                                                             │
│                                                                 │
│  ┌──────────────┐     ┌─────────────────────────┐              │
│  │ Lambda       │────▶│ OTel Collector (Fargate) │              │
│  │ (OTLP送信)   │     │ Port 4318 (OTLP HTTP)   │              │
│  └──────────────┘     │ Port 13133 (Health)      │              │
│                       └───────────┬─────────────┘              │
│                                   │                             │
│                       ┌───────────▼─────────────┐              │
│                       │ NAT Gateway              │              │
│                       └───────────┬─────────────┘              │
└───────────────────────────────────┼─────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            Grafana Cloud      Honeycomb        Datadog
```

## When VPC Deployment Is Needed

| Scenario | VPC Required | Reason |
|----------|-------------|--------|
| Lambda → External OTLP endpoint directly | ❌ | Lambda can run outside VPC |
| Lambda → VPC-internal OTel Collector | ✅ | Collector is inside VPC |
| Lambda → S3 AP + ONTAP REST API | ✅ | ONTAP API is VPC-only |
| High-security requirements (all traffic in VPC) | ✅ | Compliance requirements |

## ECS Fargate Task Definition

```json
{
  "family": "otel-collector",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "otel-collector",
      "image": "otel/opentelemetry-collector-contrib:0.152.0",
      "portMappings": [
        {"containerPort": 4318, "protocol": "tcp"},
        {"containerPort": 13133, "protocol": "tcp"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:13133/ || exit 1"],
        "interval": 10,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 15
      },
      "environment": [
        {"name": "GRAFANA_OTLP_ENDPOINT", "value": "https://otlp-gateway-prod-ap-northeast-0.grafana.net/otlp"},
        {"name": "HONEYCOMB_DATASET", "value": "fsxn-audit"}
      ],
      "secrets": [
        {"name": "GRAFANA_BASIC_AUTH", "valueFrom": "arn:aws:secretsmanager:<region>:<account-id>:secret:grafana-auth"},
        {"name": "HONEYCOMB_API_KEY", "valueFrom": "arn:aws:secretsmanager:<region>:<account-id>:secret:honeycomb-key"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/otel-collector",
          "awslogs-region": "ap-northeast-1",
          "awslogs-stream-prefix": "otel"
        }
      }
    }
  ]
}
```

## Security Group Configuration

### OTel Collector Security Group

```yaml
# Inbound Rules
- Protocol: TCP
  Port: 4318
  Source: Lambda Security Group
  Description: OTLP HTTP from Lambda

- Protocol: TCP
  Port: 13133
  Source: ALB Security Group (for health checks)
  Description: Health check from ALB

# Outbound Rules
- Protocol: TCP
  Port: 443
  Destination: 0.0.0.0/0
  Description: HTTPS to external backends (via NAT Gateway)
```

### Lambda Security Group

```yaml
# Outbound Rules
- Protocol: TCP
  Port: 4318
  Destination: OTel Collector Security Group
  Description: OTLP HTTP to Collector
```

## NAT Gateway Configuration

The OTel Collector requires a NAT Gateway to send data to external backends (Grafana Cloud, Honeycomb, Datadog).

### Subnet Layout

```
VPC CIDR: 10.0.0.0/16

Public Subnets (NAT Gateway placement):
  - 10.0.1.0/24 (AZ-a)
  - 10.0.2.0/24 (AZ-c)

Private Subnets (ECS Fargate + Lambda placement):
  - 10.0.11.0/24 (AZ-a)
  - 10.0.12.0/24 (AZ-c)
```

### Route Table (Private Subnets)

```yaml
Routes:
  - Destination: 0.0.0.0/0
    Target: nat-<gateway-id>
  - Destination: 10.0.0.0/16
    Target: local
```

## Lambda → OTel Collector Connectivity

Place the Lambda inside the VPC and connect to the Collector's internal endpoint.

### Lambda Environment Variables

```yaml
OTLP_ENDPOINT: http://<collector-private-ip>:4318
# Or use Service Discovery:
OTLP_ENDPOINT: http://otel-collector.local:4318
```

### Service Discovery (Recommended)

Use AWS Cloud Map to automatically resolve ECS task IPs:

```yaml
ServiceDiscovery:
  Namespace: fsxn-observability.local
  Service: otel-collector
  DNS: otel-collector.fsxn-observability.local
```

## Scaling Considerations

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU Utilization | > 70% | Increase task count |
| Memory Utilization | > 80% | Increase task size |
| Queue Depth | > 1000 | Adjust batch size |

### Auto Scaling Configuration

```yaml
ScalingPolicy:
  MinCapacity: 1
  MaxCapacity: 4
  TargetTrackingScaling:
    TargetValue: 70
    PredefinedMetricSpecification:
      PredefinedMetricType: ECSServiceAverageCPUUtilization
```

## Cost Estimate

| Component | Monthly Estimate (ap-northeast-1) |
|-----------|----------------------------------|
| ECS Fargate (0.5 vCPU, 1GB) | ~$15/month |
| NAT Gateway (fixed) | ~$45/month |
| NAT Gateway (data transfer) | ~$0.062/GB |
| CloudWatch Logs | ~$0.76/GB |

> **Note**: The NAT Gateway is the largest fixed cost. For low-traffic environments, running Lambda outside the VPC with direct external OTLP endpoint delivery may be more cost-effective.

## Troubleshooting

### Lambda Cannot Connect to OTel Collector

1. Verify Lambda and Collector are in the same VPC
2. Check security group inbound rules (Port 4318)
3. Verify routing from Lambda's subnet

### OTel Collector Cannot Send to External Backends

1. Verify NAT Gateway is properly configured
2. Check private subnet route table has a route to the NAT Gateway
3. Check Collector logs for connection errors

### Health Check Failures

1. Verify the Collector container is running
2. Check Port 13133 is allowed in the security group
3. Test locally with `curl http://localhost:13133/`
