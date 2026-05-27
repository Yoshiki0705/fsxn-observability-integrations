# Harvest ECS Fargate Troubleshooting Guide

## Issue: Harvest Container ExitCode 1 on ECS Fargate

### Symptoms

- ECS Deployment Circuit Breaker triggered
- Harvest container exits with `ExitCode: 1`
- No CloudWatch Logs produced (log stream not created)
- `StoppedReason: "Essential container in task exited"`

### Root Cause Analysis

Investigation identified multiple contributing factors when running NetApp Harvest (`ghcr.io/netapp/harvest`) on ECS Fargate with a custom entrypoint script.

#### Factor 1: Busybox sh Incompatibility (CRITICAL)

The Harvest container image uses `/busybox/sh` as its shell. Busybox sh is a minimal POSIX shell that does **not** support:

- Bash arrays (`read -ra`, `${ARRAY[@]}`)
- Here-strings (`<<<`)
- Process substitution
- `xargs` (not available in busybox)

**Fix**: Use POSIX-compatible constructs only (`IFS` splitting, `printf`, `tr`).

Reference: [BusyBox sh documentation](https://www.busybox.net/downloads/BusyBox.html)

#### Factor 2: Working Directory (CRITICAL)

The Harvest binary (`bin/poller`) expects to be run from `/opt/harvest/`. When using a custom entrypoint (`/busybox/sh -c`), the working directory may differ from the image's default `WORKDIR`.

**Fix**: Always `cd /opt/harvest` before executing `bin/poller`.

#### Factor 3: Correct CLI Flag (IMPORTANT)

The official Harvest CLI uses `--poller` (singular) to specify which poller(s) to start:

```bash
# Single poller
bin/poller --poller fsxn-cluster-1

# Multiple pollers (comma-separated)
bin/poller --poller fsxn-cluster-1,fsxn-cluster-2
```

The `--pollers` (plural) and `--config` flags are **not** the correct invocation for the container entrypoint.

References:
- [Harvest Containers — Official Docker Pattern](https://netapp.github.io/harvest/nightly/install/harvest-containers/)
- [Harvest Containerd — CLI Examples](https://netapp.github.io/harvest/nightly/install/containerd/)

#### Factor 4: Exporter Configuration (IMPORTANT)

The Prometheus exporter must bind to `0.0.0.0` (not localhost) for the ADOT sidecar to scrape metrics. The exporter name in the `Pollers` section must match the key in the `Exporters` section exactly.

```yaml
Exporters:
  prometheus1:          # <-- this name
    exporter: Prometheus
    addr: 0.0.0.0      # <-- required for sidecar scraping
    port_range: 12990-12999

Pollers:
  fsxn-cluster-1:
    exporters:
      - prometheus1     # <-- must match exactly
```

Reference: [Harvest Prometheus Exporter — port_range](https://netapp.github.io/harvest/nightly/prometheus-exporter/#port_range)

#### Factor 5: No Logs Produced

When the container exits before the logging driver can establish a connection, no CloudWatch log stream is created. This happens when:

1. The entrypoint script has a syntax error (shell exits immediately)
2. The `bin/poller` binary fails to parse `harvest.yml` (exits before writing logs)

**Workaround**: Add `echo` statements at the beginning of the script and ensure the log group exists before deployment.

### Official Harvest Container Patterns

| Pattern | Use Case | Reference |
|---------|----------|-----------|
| Docker Compose (1 poller/container) | Production recommended | [harvest-containers](https://netapp.github.io/harvest/nightly/install/harvest-containers/) |
| Single container, multiple pollers | ECS Fargate (cost optimization) | Custom (this project) |
| Kubernetes | K8s environments | [K8 install](https://netapp.github.io/harvest/nightly/install/k8/) |

### harvest.yml Reference for FSx ONTAP

```yaml
Pollers:
  fsxn-cluster-1:
    datacenter: fsxn-1
    addr: <management-endpoint>
    auth_style: basic_auth
    username: fsxadmin
    password: <password>
    use_insecure_tls: true    # Required for FSx ONTAP
    collectors:
      - Rest
      - RestPerf
    exporters:
      - prometheus1

Exporters:
  prometheus1:
    exporter: Prometheus
    addr: 0.0.0.0
    port_range: 12990-12999

Defaults:
  use_insecure_tls: true      # Required for FSx ONTAP
```

Key points:
- `use_insecure_tls: true` is **required** for FSx ONTAP (self-signed certificates)
- `addr: 0.0.0.0` in the exporter is required for sidecar scraping
- `collectors: [Rest, RestPerf]` — ZAPI is deprecated for FSx ONTAP
- `auth_style: basic_auth` with fsxadmin credentials

Reference: [Amazon FSx for ONTAP — Harvest Preparation](https://netapp.github.io/harvest/nightly/prepare-fsx-clusters/)

### Supported Dashboards for FSx ONTAP

Not all Harvest dashboards work with FSx ONTAP. The following are confirmed compatible:

- ONTAP: cDOT
- ONTAP: Cluster
- ONTAP: Data Protection
- ONTAP: Datacenter
- ONTAP: FlexCache
- ONTAP: FlexGroup
- ONTAP: FPolicy
- ONTAP: LUN
- ONTAP: NFS Troubleshooting
- ONTAP: Quota
- ONTAP: Security
- ONTAP: SVM
- ONTAP: Volume
- ONTAP: Volume by SVM
- ONTAP: Volume Deep Dive

Reference: [FSx ONTAP — Supported Harvest Dashboards](https://netapp.github.io/harvest/nightly/prepare-fsx-clusters/#supported-harvest-dashboards)

### ECS-Specific Considerations

#### CPU Architecture

`ghcr.io/netapp/harvest` is built for `linux/amd64`. ECS Fargate defaults to x86_64, which is compatible. If using Graviton (ARM64), the container will fail with ExitCode 1.

Reference: [Fix ECS Exit code 1 — CPU Architecture Mismatch](https://openillumi.com/en/en-ecs-exit-code-1-exec-format-error-arch-fix/)

#### Secrets Manager Injection

ECS `Secrets` (ValueFrom) requires network access to Secrets Manager at task startup. In private subnets, a Secrets Manager VPC Endpoint is required. If DNS propagation is incomplete, the task fails with `ResourceInitializationError`.

Reference: [AWS ECS Fargate ResourceInitializationError](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stopped-task-errors.html)

#### VPC Endpoint DNS Propagation

After creating VPC Endpoints (via Stack 1), DNS propagation may take 1-5 minutes. ECS tasks launched immediately after endpoint creation may fail to resolve endpoint DNS names.

**Workaround**: Add a CloudFormation `DependsOn` or wait between Stack 1 and Stack 3 deployment.

### Deployment Verification Checklist

Before deploying Stack 3 (observability):

- [ ] Stack 1 VPC Endpoints are in `available` state
- [ ] Secrets Manager secret exists and contains valid JSON (`{"username": "fsxadmin", "password": "..."}`)
- [ ] FSx ONTAP security group allows inbound TCP/443 from Harvest task security group
- [ ] Harvest image tag exists (`latest` recommended for initial deployment)
- [ ] Private subnets have NAT Gateway route for GHCR image pull (or ECR VPC Endpoint for cached images)
