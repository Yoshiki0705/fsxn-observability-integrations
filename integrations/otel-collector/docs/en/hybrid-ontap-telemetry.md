# Hybrid ONTAP Telemetry with OpenTelemetry Collector

## Applicability

The OTLP + Collector pattern demonstrated in this repository for FSx for ONTAP can be extended to other ONTAP deployment models:

| ONTAP Deployment | Collector Placement | Network Path |
|-----------------|--------------------|--------------| 
| FSx for ONTAP (AWS) | ECS Fargate / EC2 in same VPC | VPC internal |
| Cloud Volumes ONTAP (AWS/Azure/GCP) | Cloud-native container in same VNet/VPC | Cloud internal |
| On-premises ONTAP | Local VM/container | Direct Connect / VPN to cloud backends |

## Common Elements

Regardless of ONTAP deployment model, the following remain consistent:

- **ONTAP telemetry sources**: Audit logs, EMS, FPolicy
- **Normalized schema**: Same OTLP attribute mapping (event.type, user.name, fsxn.operation, etc.)
- **Collector config**: Same exporter configuration for backends
- **Backend independence**: Same vendor-neutral routing pattern

## Key Differences by Deployment

| Aspect | FSx for ONTAP | CVO | On-Premises |
|--------|--------------|-----|-------------|
| Audit log access | S3 Access Point | S3/Blob | NFS/CIFS mount |
| EMS delivery | API Gateway webhook | API Gateway / Cloud Function | Local webhook receiver |
| FPolicy | ECS Fargate server | Cloud container | Local server |
| Collector hosting | ECS Fargate | Cloud container | VM / bare metal |
| Network to backends | NAT Gateway / VPC Endpoint | Cloud NAT | Direct Connect / Internet |

## Future Work

- Detailed implementation guides for CVO and on-premises ONTAP
- Collector placement patterns for hybrid environments
- Network connectivity patterns (Direct Connect, VPN, PrivateLink)
- Disconnected site behavior and store-and-forward patterns

> This document outlines the architectural direction. Implementation details for non-FSx deployments are planned for future articles.

---

## Overview

ONTAP runs in multiple deployment models. This guide covers how to collect and normalize telemetry across all ONTAP environments using a consistent OTel-based pipeline.

## Deployment Patterns

### FSx for ONTAP (AWS Managed)

```
┌─────────────────────────────────────────────────────────────────┐
│  AWS Account                                                     │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────────┐  │
│  │ FSx ONTAP    │────▶│ S3 Bucket    │────▶│ Lambda         │  │
│  │ (Audit logs) │     │ (Raw logs)   │     │ (Parse + OTLP) │  │
│  └──────────────┘     └──────────────┘     └───────┬────────┘  │
│                                                     │            │
│  ┌──────────────┐     ┌──────────────┐             │            │
│  │ FSx ONTAP    │────▶│ API Gateway  │────▶ Lambda ─┤            │
│  │ (EMS webhook)│     │              │             │            │
│  └──────────────┘     └──────────────┘             │            │
│                                                     │ OTLP/HTTP  │
│  ┌──────────────┐     ┌──────────────┐             │            │
│  │ FSx ONTAP    │────▶│ ECS Fargate  │────▶ SQS ──▶│ Lambda    │
│  │ (FPolicy TCP)│     │ (FP Server)  │             │            │
│  └──────────────┘     └──────────────┘             │            │
│                                                     ▼            │
│                                            ┌────────────────┐   │
│                                            │ OTel Collector  │   │
│                                            │ (ECS Fargate)   │   │
│                                            └───────┬────────┘   │
│                                                    │             │
└────────────────────────────────────────────────────┼─────────────┘
                                                     │
                                          ┌──────────┼──────────┐
                                          ▼          ▼          ▼
                                      Datadog    Grafana   Honeycomb
```

**Key characteristics:**
- Fully serverless ingestion (Lambda + ECS Fargate)
- S3 as audit log buffer (EventBridge trigger or scheduled polling)
- Collector runs as ECS Fargate service in same VPC
- No EC2 instances required

### Cloud Volumes ONTAP (Self-Managed on Cloud)

```
┌─────────────────────────────────────────────────────────────────┐
│  AWS / Azure / GCP Account                                       │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────────┐  │
│  │ CVO ONTAP    │────▶│ Cloud Storage│────▶│ Serverless Fn  │  │
│  │ (Audit logs) │     │ (S3/Blob/GCS)│     │ (Parse + OTLP) │  │
│  └──────────────┘     └──────────────┘     └───────┬────────┘  │
│                                                     │            │
│  ┌──────────────┐                                   │ OTLP/HTTP  │
│  │ CVO ONTAP    │────▶ EMS Webhook ────────────────▶│            │
│  │ (EMS)        │                                   │            │
│  └──────────────┘                                   ▼            │
│                                            ┌────────────────┐   │
│                                            │ OTel Collector  │   │
│                                            │ (Container/VM)  │   │
│                                            │ Same VPC/VNet   │   │
│                                            └───────┬────────┘   │
└────────────────────────────────────────────────────┼─────────────┘
                                                     │
                                          ┌──────────┼──────────┐
                                          ▼          ▼          ▼
                                      Datadog    Splunk    Elastic
```

**Key characteristics:**
- Collector deployed in same VPC/VNet as CVO
- Cloud-native compute for ingestion (Lambda/Functions/Cloud Run)
- Storage varies by cloud provider (S3/Blob/GCS)
- Same OTLP schema regardless of cloud provider

### On-Premises ONTAP

```
┌─────────────────────────────────────────────────────────────────┐
│  On-Premises Data Center                                         │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────────┐  │
│  │ ONTAP Cluster│────▶│ NFS/CIFS     │────▶│ Log Collector  │  │
│  │ (Audit logs) │     │ Share        │     │ (VM/Container) │  │
│  └──────────────┘     └──────────────┘     └───────┬────────┘  │
│                                                     │            │
│  ┌──────────────┐                                   │ OTLP/HTTP  │
│  │ ONTAP Cluster│────▶ EMS/Syslog ─────────────────▶│            │
│  │ (EMS)        │                                   │            │
│  └──────────────┘                                   ▼            │
│                                            ┌────────────────┐   │
│                                            │ OTel Collector  │   │
│                                            │ (VM/Container)  │   │
│                                            │ On-prem         │   │
│                                            └───────┬────────┘   │
└────────────────────────────────────────────────────┼─────────────┘
                                                     │
                                          Direct Connect / VPN / Proxy
                                                     │
                                          ┌──────────┼──────────┐
                                          ▼          ▼          ▼
                                      Datadog    Splunk    Grafana
                                      (Cloud)    (Cloud)   (Cloud)
```

**Key characteristics:**
- Collector runs as VM or container on-premises
- Audit logs accessed via NFS/CIFS mount (not S3)
- Network connectivity to cloud backends via Direct Connect, VPN, or proxy
- May require local buffering for network interruptions

## Common Normalized Schema

Regardless of ONTAP deployment model, all telemetry is normalized to the same OTLP schema:

```yaml
# Common attributes across all ONTAP types
resource:
  service.name: "fsxn-audit"          # or fsxn-ems, fsxn-fpolicy
  service.version: "1.0.0"
  deployment.environment: "production"
  ontap.cluster.name: "<cluster-name>"
  ontap.svm.name: "<svm-name>"
  ontap.deployment.type: "fsx"        # fsx | cvo | onprem
  cloud.provider: "aws"              # aws | azure | gcp | onprem
  cloud.region: "ap-northeast-1"     # or azure region, etc.

log_record:
  timestamp: "<ontap-event-timestamp>"
  severity_number: 9                  # INFO
  body: "<original event content>"
  attributes:
    event.type: "file.read"
    event.id: "<unique-event-id>"
    file.path: "/vol1/data/report.xlsx"
    user.name: "DOMAIN\\username"
    source.address: "<client-ip>"
```

### Schema Differences by Deployment Type

| Attribute | FSx for ONTAP | Cloud Volumes ONTAP | On-Prem ONTAP |
|-----------|---------------|--------------------:|---------------|
| `ontap.deployment.type` | `fsx` | `cvo` | `onprem` |
| `cloud.provider` | `aws` | `aws` / `azure` / `gcp` | `onprem` |
| `cloud.region` | AWS region | Cloud region | `<datacenter-id>` |
| `ontap.filesystem.id` | `fs-0123456789abcdef0` | Instance ID | Cluster serial |
| Audit log source | S3 bucket | Cloud storage | NFS/CIFS share |

## Network Connectivity Patterns

### FSx for ONTAP → Cloud Backends

| Pattern | Use Case | Latency | Cost |
|---------|----------|---------|------|
| VPC → Internet (NAT GW) | Default for cloud backends | Low | NAT GW hourly + data |
| VPC → PrivateLink | Supported backends (Datadog) | Lowest | PrivateLink hourly |
| VPC → VPC Peering | Collector in separate VPC | Low | Data transfer only |

### On-Prem → Cloud Backends

| Pattern | Use Case | Latency | Cost |
|---------|----------|---------|------|
| Direct Connect | High volume, low latency | Lowest | DC port + data |
| Site-to-Site VPN | Moderate volume | Medium | VPN hourly + data |
| HTTPS Proxy | Restricted networks | Higher | Proxy infrastructure |
| Local buffer + batch | Intermittent connectivity | Variable | Local storage |

### Collector Placement for On-Prem

```
Option A: Collector on-prem (recommended for high volume)
  ONTAP → [local network] → Collector → [WAN] → Cloud backends
  Pros: Low latency collection, local buffering
  Cons: On-prem infrastructure to manage

Option B: Collector in cloud (recommended for simplicity)
  ONTAP → [WAN] → Collector (cloud) → Cloud backends
  Pros: No on-prem Collector management
  Cons: WAN dependency for collection, higher latency

Option C: Dual Collector (recommended for hybrid)
  ONTAP → [local] → Collector (on-prem) → [WAN] → Collector (cloud) → Backends
  Pros: Local buffering + cloud routing flexibility
  Cons: Two Collectors to manage
```

## Collector Placement Decision Tree

```
┌─────────────────────────────────────────────┐
│ Where does ONTAP run?                        │
└──────────────────┬──────────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
   FSx ONTAP    CVO ONTAP    On-Prem
     │             │             │
     ▼             ▼             ▼
┌──────────┐ ┌──────────┐ ┌──────────────────────┐
│ Collector│ │ Collector│ │ Is WAN reliable?      │
│ in same  │ │ in same  │ └──────────┬───────────┘
│ VPC      │ │ VPC/VNet │      ┌─────┴─────┐
│ (Fargate)│ │(Container│      │           │
└──────────┘ │ or VM)   │     YES          NO
             └──────────┘      │           │
                               ▼           ▼
                        ┌──────────┐ ┌──────────┐
                        │ Collector│ │ Collector│
                        │ in cloud │ │ on-prem  │
                        │ (simple) │ │ (buffer) │
                        └──────────┘ └──────────┘
```

## Relationship to Cloud Insights / BlueXP

### Complementary, Not Replacement

| Capability | Cloud Insights / BlueXP | This Project (OTel) |
|-----------|------------------------|---------------------|
| **Purpose** | Infrastructure monitoring, capacity planning | Audit compliance, security telemetry |
| **Data scope** | Performance metrics, topology | Audit logs, EMS events, FPolicy |
| **Backends** | NetApp Cloud Insights | Any OTLP-compatible backend |
| **Deployment** | SaaS (managed by NetApp) | Self-managed (your infrastructure) |
| **Customization** | Limited to CI capabilities | Full control over routing/filtering |
| **Cost model** | Per-node licensing | Infrastructure cost only |

### When to Use Each

**Use Cloud Insights / BlueXP for:**
- Storage performance monitoring (IOPS, latency, throughput)
- Capacity planning and forecasting
- Infrastructure topology visualization
- NetApp-specific health checks and recommendations

**Use OTel Collector pipeline for:**
- Audit log delivery to compliance backends
- Security event fan-out to multiple SIEM/observability tools
- Custom filtering, redaction, and enrichment
- Multi-vendor backend strategy
- FPolicy-based ransomware detection pipelines

**Use both together:**
- Cloud Insights for infrastructure health
- OTel pipeline for audit/security telemetry
- Correlated investigation: CI shows "what happened to storage" + OTel shows "who did what"

## Future Considerations

### Planned Enhancements

| Enhancement | Status | Impact |
|-------------|--------|--------|
| ONTAP native OTLP export | Under discussion | Eliminates Lambda parsing layer |
| FSx ONTAP S3 Event Notifications | Not available | Would replace polling with push |
| OTel Collector Kubernetes operator | Available | Simplifies on-prem/EKS deployment |
| Collector config hot-reload | Available (0.100+) | Zero-downtime config changes |

### Migration Path: Direct Send → OTel Collector

For environments currently using Direct Send:

1. Deploy Collector alongside existing Lambda
2. Configure Lambda to send to both (dual-write period)
3. Validate data in Collector-delivered backends
4. Cut over: Lambda sends only to Collector
5. Decommission direct-send code path

### Multi-Cloud Unified View

For organizations running ONTAP across multiple clouds:

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ FSx ONTAP│  │ CVO (AWS)│  │CVO(Azure)│
│ (AWS)    │  │          │  │          │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │
     ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Collector│  │ Collector│  │ Collector│
│ (AWS)    │  │ (AWS)    │  │ (Azure)  │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │
     └──────────────┼──────────────┘
                    │
                    ▼
         ┌────────────────────┐
         │ Central Backend(s) │
         │ Unified dashboards │
         │ Cross-cloud queries│
         └────────────────────┘
```

All Collectors use the same normalized schema, enabling cross-cloud queries using `ontap.deployment.type` and `cloud.provider` attributes.
