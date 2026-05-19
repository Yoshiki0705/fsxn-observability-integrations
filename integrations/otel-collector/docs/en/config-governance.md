# Config Governance Guide: OTel Collector

## Config File Ownership

| File | Owner | Approval Required |
|------|-------|-------------------|
| `otel-collector-config.yaml` | Platform / SRE team | PR review + CI validation |
| `otel-collector-config-<env>.yaml` | Platform / SRE team | PR review + CI validation |
| `.env` / `.env.<backend>` | Security team | Secrets Manager rotation |
| `template-collector.yaml` (CFn) | Infrastructure team | Architecture review |

## CI Validation

### Validate Config in CI Pipeline

```yaml
# .github/workflows/validate-otel-config.yaml
name: Validate OTel Collector Config
on:
  pull_request:
    paths:
      - 'integrations/otel-collector/otel-collector-config*.yaml'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Pull OTel Collector image
        run: docker pull otel/opentelemetry-collector-contrib:0.152.0

      - name: Validate config syntax
        run: |
          docker run --rm \
            -v $(pwd)/integrations/otel-collector:/config \
            otel/opentelemetry-collector-contrib:0.152.0 \
            validate --config /config/otel-collector-config.yaml

      - name: Validate all config variants
        run: |
          for config in integrations/otel-collector/otel-collector-config*.yaml; do
            echo "Validating: $config"
            docker run --rm \
              -v $(pwd)/integrations/otel-collector:/config \
              otel/opentelemetry-collector-contrib:0.152.0 \
              validate --config /config/$(basename $config)
          done
```

### Local Validation

```bash
# Validate config syntax
docker run --rm \
  -v $(pwd)/integrations/otel-collector:/config \
  otel/opentelemetry-collector-contrib:0.152.0 \
  validate --config /config/otel-collector-config.yaml

# Note: The binary is `otelcol-contrib` in the contrib distribution.
# For the core distribution, use `otelcol validate --config=<path>`.
# Validation may report errors for unresolved ${env:...} variables —
# this is expected when secrets are not available in CI.
```

> **Note**: Config validation with `validate` checks YAML syntax and component references, but may report errors for unresolved `${env:...}` variables. This is expected when validating outside the runtime environment.

## Environment Separation

### Directory Structure

```
integrations/otel-collector/
├── otel-collector-config.yaml           # Default (dev/local)
├── otel-collector-config-staging.yaml   # Staging
├── otel-collector-config-prod.yaml      # Production
├── otel-collector-config-datadog.yaml   # Datadog backend
├── otel-collector-config-triple.yaml    # Triple backend
└── .env.example                         # Template (no secrets)
```

### Environment-Specific Differences

| Setting | Dev | Staging | Production |
|---------|-----|---------|------------|
| Batch timeout | 1s | 5s | 5s |
| Batch size | 100 | 500 | 1000 |
| Log level | debug | info | info |
| Retry max | 1 | 3 | 5 |
| Health check | enabled | enabled | enabled |
| Internal metrics | enabled | enabled | enabled |
| Exporters | 1 (local) | 1-2 | All configured |

## Secret Management Policy

### Rules

1. **Never commit secrets** to version control
2. **Use Secrets Manager** for all backend credentials
3. **Reference via environment variables**: `${env:SECRET_NAME}`
4. **Rotate every 90 days** minimum
5. **Separate secrets per environment** (dev/staging/prod)
6. **Audit access** via CloudTrail

### Secret Naming Convention

```
fsxn/otel/<environment>/<backend>/<credential-type>
```

Examples:
- `fsxn/otel/prod/grafana/basic-auth`
- `fsxn/otel/prod/honeycomb/api-key`
- `fsxn/otel/prod/datadog/api-key`

## Staged Rollout / Canary Collector

### Canary Deployment Strategy

```
┌─────────────┐     ┌──────────────────┐
│   Lambda    │────▶│ Canary Collector  │──▶ Backend (5% traffic)
│  (all)      │     │ (new config)      │
│             │────▶│ Stable Collector  │──▶ Backend (95% traffic)
└─────────────┘     │ (current config)  │
                    └──────────────────┘
```

### Implementation with ECS

```yaml
# Deploy canary task with new config
CanaryService:
  Type: AWS::ECS::Service
  Properties:
    ServiceName: otel-collector-canary
    DesiredCount: 1
    TaskDefinition: !Ref CanaryTaskDefinition

# Stable service continues with current config
StableService:
  Type: AWS::ECS::Service
  Properties:
    ServiceName: otel-collector-stable
    DesiredCount: 2
    TaskDefinition: !Ref StableTaskDefinition
```

### Canary Validation Steps

1. Deploy canary with new config (1 task)
2. Route 5-10% of traffic to canary (via weighted target group or DNS)
3. Monitor for 30 minutes:
   - Exporter error count = 0
   - Latency within baseline
   - No dropped logs
4. If healthy: promote canary config to stable
5. If unhealthy: terminate canary, rollback

## Rollback Process

### Config Rollback

```bash
# 1. Identify last known good config
git log --oneline integrations/otel-collector/otel-collector-config-prod.yaml

# 2. Revert to previous version
git checkout <commit-hash> -- integrations/otel-collector/otel-collector-config-prod.yaml

# 3. Validate reverted config
docker run --rm \
  -v $(pwd)/integrations/otel-collector:/config \
  otel/opentelemetry-collector-contrib:0.152.0 \
  validate --config /config/otel-collector-config-prod.yaml

# 4. Deploy reverted config
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment
```

### Automated Rollback Trigger

```yaml
# CloudWatch Alarm → SNS → Lambda (auto-rollback)
ExporterErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: otel-collector-exporter-errors
    MetricName: otelcol_exporter_send_failed_log_records
    Namespace: OTelCollector
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 2
    Threshold: 100
    ComparisonOperator: GreaterThanThreshold
    AlarmActions:
      - !Ref RollbackSNSTopic
```

## Change Approval Checklist

Before merging any Collector config change:

- [ ] Config validated with `otelcol validate --config`
- [ ] No hardcoded secrets (grep for API keys, tokens)
- [ ] Environment variables reference Secrets Manager
- [ ] Batch settings appropriate for target environment
- [ ] Exporter endpoints correct for target environment
- [ ] Rollback plan documented in PR description
- [ ] Canary deployment planned (for production changes)
- [ ] Monitoring dashboards updated if new exporters added
- [ ] Security team notified if credential changes involved
- [ ] At least 1 reviewer from platform team approved

## Auditability of Routing Changes

### Git History as Audit Trail

```bash
# View routing change history
git log --all --oneline -- 'integrations/otel-collector/otel-collector-config*.yaml' \
  | grep -i "route\|export\|pipeline\|backend"
```

### Change Documentation Template

Each PR modifying routing must include:

```markdown
## Routing Change Summary
- **What changed**: Added/removed/modified exporter for <backend>
- **Why**: <business justification>
- **Impact**: Logs now route to <new destination>
- **Rollback**: Revert commit <hash> and force-redeploy
- **Tested in**: staging / canary
```

## Per-Backend Routing Policy

| Backend | Data Types | Retention | SLA | Notes |
|---------|-----------|-----------|-----|-------|
| Security SIEM | Delete, permission change, failed access | 1 year | 99.9% | Compliance requirement |
| Grafana Cloud | All events (search/alerting) | 30 days | 99.5% | Operational visibility |
| Honeycomb | All events (exploration) | 60 days | 99.5% | Deep analysis |
| Archive (S3) | All events (raw) | 7 years | 99.99% | Compliance/legal hold |
| Cheap storage | Read events (high volume) | 7 days | 99% | Cost optimization |

### Routing Decision Tree

```
Event arrives at Collector
  │
  ├── Is it a security event? (delete/permission/failed access)
  │     └── YES → Security SIEM + Grafana + Archive
  │
  ├── Is it a read event? (high volume)
  │     └── YES → Cheap storage only (or sampled to Grafana)
  │
  └── All other events
        └── Grafana + Honeycomb + Archive
```
