# Splunk Forensic Investigation Searches

DII Storage Workload Security equivalent forensic investigation views for FSx for ONTAP audit logs in Splunk.

## Prerequisites

- FSx for ONTAP audit logs shipped to Splunk via the `integrations/splunk-serverless/` pipeline
- Default index: `fsxn_audit` (configurable via `SPLUNK_INDEX` environment variable in the Lambda)

## Investigation Workflow

The same 4-step investigation flow used across all vendors in this project:

| Step | Search File | Purpose |
|------|-------------|---------|
| 1 | `user-timeline.spl` | Overview of a user's activity volume over time |
| 2 | `all-activity.spl` | Full event stream for a user/time window |
| 3 | `ip-drill-down.spl` | Identify access source IPs, detect unusual origins |
| 4 | `file-entity-history.spl` | All operations on a specific file path |

## Usage in Dashboard Studio

Compose these into a Splunk Dashboard Studio dashboard with input tokens:

```xml
<!-- Input tokens -->
<input type="text" token="user">
  <label>Username</label>
  <default>*</default>
</input>
<input type="text" token="client_ip">
  <label>Client IP</label>
  <default>*</default>
</input>
<input type="text" token="path">
  <label>File Path</label>
  <default>*</default>
</input>
```

Each `.spl` file uses `$user$`, `$client_ip$`, and `$path$` as token placeholders. Replace with actual values or use as Dashboard Studio tokens.

## Equivalent on Other Vendors

| Vendor | Equivalent Artifact |
|--------|-------------------|
| Datadog | [`integrations/datadog/dashboards/forensics-dashboard.json`](../../datadog/dashboards/) |
| Grafana | [`integrations/grafana/dashboards/forensics-investigation.json`](../../grafana/dashboards/forensics-investigation.json) |
| Elastic | [Kibana Saved Searches (KQL)](../../elastic/docs/en/setup-guide.md#forensic-investigation-kibana-discoverlens) |

> See [AWS-Native Alternative Matrix — Forensics Per-Vendor Reference](../../../docs/en/native-alternative-matrix.md#forensics-dashboard--per-vendor-reference) for the full comparison.
