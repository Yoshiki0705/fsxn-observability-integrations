# FSxN Grafana Alerting Rules

## Overview

Three alert rules for FSx for ONTAP audit log monitoring:

1. **Ransomware Detection (ARP)** — ONTAP Anti-Ransomware Protection volume state change
2. **Quota Soft Limit Exceeded** — WAFL quota threshold warning
3. **Failed Access Spike** — >10 failed access attempts in 5 minutes

## Provisioning

```bash
export GRAFANA_SA_TOKEN="glsa_..."
export GRAFANA_URL="https://your-instance.grafana.net"
bash integrations/grafana/scripts/create-alerts.sh
```

## Alert Provisioning Details

| Setting | Value | Rationale |
|---------|-------|-----------|
| `noDataState` | OK | Absence of matching events is normal operation |
| `execErrState` | Error | Query execution errors need operator attention |
| Folder | FSxN Alerts | Dedicated folder for FSxN rules |
| Evaluation interval | 1 minute | Balance between detection speed and query load |

## What Is NOT Provisioned

The script provisions **alert rules only**. The following must be configured separately in the Grafana UI:

- **Contact points** (Slack, PagerDuty, email, webhook)
- **Notification policies** (routing by severity/team label)
- **Mute timings** (maintenance windows)
- **Silences** (temporary suppression)

Without contact points and notification policies, alerts will fire but no notifications will be delivered.

## Threshold Tuning

The default thresholds are starter values:

| Alert | Default | Tune based on |
|-------|---------|---------------|
| Ransomware Detection | > 0 events | Should remain at 0 (any ARP event is critical) |
| Quota Warning | > 0 events | May increase if quota warnings are frequent and expected |
| Failed Access Spike | > 10 in 5 min | Adjust per SVM, workload, and normal user behavior |

## API Compatibility

This script uses Grafana's Alerting Provisioning HTTP API (`/api/v1/provisioning`). Grafana 13+ introduces newer `/apis` routes while legacy `/api` routes remain available. Check your Grafana Cloud version if provisioning fails.

## Files

- `rules.yaml` — Declarative alert rule definitions (Grafana unified alerting format)
- `../scripts/create-alerts.sh` — Provisioning script using Grafana HTTP API
