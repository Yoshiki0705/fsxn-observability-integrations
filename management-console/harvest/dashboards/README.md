# Harvest Grafana Dashboards for FSx ONTAP

This directory contains Grafana dashboard JSON files from the [NetApp Harvest](https://github.com/NetApp/harvest) project, customized for Amazon FSx for NetApp ONTAP monitoring via Amazon Managed Grafana (AMG).

## Supported Harvest Dashboards for FSx ONTAP

NetApp Harvest provides 60+ pre-built Grafana dashboards for ONTAP. However, FSx for ONTAP is a managed service with limited access to certain subsystems. The following dashboards are **supported and recommended** for FSx ONTAP deployments.

### Dashboard Categories (Minimum 20 Required)

| Category | Dashboard | Filename | Description |
|----------|-----------|----------|-------------|
| **Volume Performance** | Volume Performance | `volume_performance.json` | Combined IOPS, throughput, latency overview |
| | Volume IOPS | `volume_iops.json` | Read/write/other IOPS per volume |
| | Volume Throughput | `volume_throughput.json` | Read/write data rate per volume |
| | Volume Latency | `volume_latency.json` | Read/write/other latency per volume |
| | Volume Top N | `volume_top_n.json` | Top volumes by IOPS, throughput, latency |
| **Aggregate Utilization** | Aggregate Capacity | `aggregate_capacity.json` | Total/used/available capacity per aggregate |
| | Aggregate Utilization | `aggregate_utilization.json` | Percentage utilization and trends |
| | Aggregate Growth | `aggregate_growth.json` | Capacity growth rate and projections |
| | Aggregate Space Savings | `aggregate_space_savings.json` | Deduplication and compression savings |
| **SVM Health** | SVM Overview | `svm_overview.json` | SVM state, protocols, volume count |
| | SVM NFS Operations | `svm_nfs_operations.json` | NFS operation types and latency |
| | SVM CIFS Operations | `svm_cifs_operations.json` | CIFS/SMB operation types and latency |
| | SVM iSCSI Operations | `svm_iscsi_operations.json` | iSCSI read/write operations and latency |
| **Network Interfaces** | LIF Throughput | `network_lif_throughput.json` | Network interface data throughput |
| | LIF Errors | `network_lif_errors.json` | Network interface error counts |
| | Port Status | `network_port_status.json` | Physical/logical port up/down status |
| | LIF Packets | `network_lif_packets.json` | Packet counts per network interface |
| **Disk Status** | Disk Health | `disk_health.json` | Disk health state and SMART status |
| | Disk Utilization | `disk_utilization.json` | Disk busy percentage and queue depth |
| | Disk Errors | `disk_errors.json` | Disk error counts and types |
| | Disk Spare Count | `disk_spare_count.json` | Available spare disk inventory |

### Dashboards NOT Supported on FSx ONTAP

The following Harvest dashboards rely on features not available in FSx for ONTAP:

| Dashboard | Reason |
|-----------|--------|
| Cluster Hardware | FSx manages hardware — no user access |
| Shelf/Bay Status | Physical shelf management not exposed |
| MetroCluster | Not available on FSx ONTAP |
| FabricPool Tiering | FSx manages tiering internally |
| Node-level CPU/Memory | Node metrics not exposed to users |
| Cluster Peer | Cross-cluster peering managed by AWS |
| AutoSupport | Managed by AWS, not user-accessible |

## How to Download Dashboard JSON from Harvest GitHub

### Option 1: Download Individual Dashboards (Recommended)

```bash
# Base URL for Harvest Grafana dashboards
HARVEST_REPO="https://raw.githubusercontent.com/NetApp/harvest/main/grafana/dashboards/cmode"

# Download volume performance dashboards
curl -sL "${HARVEST_REPO}/volume.json" -o volume_performance.json
curl -sL "${HARVEST_REPO}/volume_top.json" -o volume_top_n.json

# Download aggregate dashboards
curl -sL "${HARVEST_REPO}/aggregate.json" -o aggregate_capacity.json

# Download SVM dashboards
curl -sL "${HARVEST_REPO}/svm.json" -o svm_overview.json
curl -sL "${HARVEST_REPO}/nfs.json" -o svm_nfs_operations.json
curl -sL "${HARVEST_REPO}/cifs.json" -o svm_cifs_operations.json
curl -sL "${HARVEST_REPO}/iscsi.json" -o svm_iscsi_operations.json

# Download network dashboards
curl -sL "${HARVEST_REPO}/lif.json" -o network_lif_throughput.json
curl -sL "${HARVEST_REPO}/network.json" -o network_port_status.json

# Download disk dashboards
curl -sL "${HARVEST_REPO}/disk.json" -o disk_health.json
```

### Option 2: Clone Entire Harvest Repository

```bash
# Clone Harvest repo (sparse checkout for dashboards only)
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/NetApp/harvest.git /tmp/harvest

cd /tmp/harvest
git sparse-checkout set grafana/dashboards/cmode

# Copy relevant dashboards
cp grafana/dashboards/cmode/*.json \
  /path/to/management-console/harvest/dashboards/

# Clean up
rm -rf /tmp/harvest
```

### Option 3: Use Harvest CLI Export

If you have Harvest installed locally:

```bash
# Export dashboards from a running Harvest instance
harvest grafana export --directory ./dashboards/
```

## Customizing Dashboards for FSx ONTAP

After downloading, dashboards need customization to work with FSx ONTAP and AMP:

### Step 1: Remove Unsupported Panels

Some panels reference metrics not available on FSx ONTAP. Remove or hide them:

```bash
# Use jq to remove panels referencing unsupported metrics
jq '
  .panels |= map(
    select(
      (.targets // [] | map(.expr // "") | join("")) |
      test("node_cpu|node_memory|shelf_|metrocluster_|fabricpool_") | not
    )
  )
' input_dashboard.json > output_dashboard.json
```

**Metrics to remove** (not available on FSx ONTAP):
- `node_cpu_*` — Node CPU metrics (managed by AWS)
- `node_memory_*` — Node memory metrics (managed by AWS)
- `shelf_*` — Physical shelf metrics
- `metrocluster_*` — MetroCluster metrics
- `fabricpool_*` — FabricPool tiering metrics
- `cluster_peer_*` — Cluster peering metrics
- `autosupport_*` — AutoSupport metrics

### Step 2: Update Data Source References

The import script (`import-dashboards.sh`) handles this automatically, but for manual customization:

```bash
# Replace all datasource references with AMP
jq '
  walk(
    if type == "object" and has("datasource") then
      if .datasource | type == "string" then
        .datasource = "Amazon Managed Prometheus"
      elif .datasource | type == "object" then
        .datasource = {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}
      else .
      end
    else .
    end
  )
' dashboard.json > dashboard_patched.json
```

### Step 3: Adjust Variable Templates

Harvest dashboards use template variables that may need adjustment for FSx ONTAP:

```bash
# Update cluster variable to use FSx file system identifier
jq '
  .templating.list |= map(
    if .name == "Cluster" then
      .query = "label_values(volume_read_ops, cluster)"
    elif .name == "Datacenter" then
      .query = "label_values(volume_read_ops, datacenter)"
    else .
    end
  )
' dashboard.json > dashboard_updated.json
```

### Step 4: Validate Customized Dashboard

```bash
# Validate JSON syntax
jq empty dashboard.json

# Check for remaining unsupported metric references
jq -r '
  [.panels[].targets[]?.expr // empty] |
  map(select(test("node_cpu|shelf_|metrocluster_"))) |
  if length > 0 then
    "WARNING: Found unsupported metrics:\n" + join("\n")
  else
    "OK: No unsupported metrics found"
  end
' dashboard.json
```

## Panel Embed URL Format for ToolJet Integration

### URL Format

AMG supports embedding individual panels via the solo panel URL:

```
https://<amg-workspace-url>/d-solo/<dashboard-uid>?orgId=1&panelId=<panel-id>&from=<start>&to=<end>&refresh=<interval>
```

### Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `<amg-workspace-url>` | AMG workspace base URL | `g-abc123.grafana-workspace.ap-northeast-1.amazonaws.com` |
| `<dashboard-uid>` | Dashboard unique identifier (assigned on import) | `fsxn-vol-perf` |
| `<panel-id>` | Panel ID within the dashboard | `2` |
| `from` | Start time (relative or absolute) | `now-1h`, `now-7d` |
| `to` | End time | `now` |
| `refresh` | Auto-refresh interval | `1m`, `5m`, `30s` |
| `var-Volume` | Template variable filter | `vol_data_01` |
| `var-SVM` | SVM filter variable | `svm-prod-01` |

### ToolJet iframe Component Configuration

In ToolJet, use an **iframe** component with the embed URL:

```html
<iframe
  src="https://<amg-workspace-url>/d-solo/<dashboard-uid>?orgId=1&panelId=<panel-id>&from=now-1h&to=now&refresh=1m&var-Volume={{selectedVolume}}"
  width="100%"
  height="300"
  frameborder="0"
></iframe>
```

### Example Embed URLs by Use Case

#### Volume Detail Page — IOPS Panel

```
https://<amg-url>/d-solo/vol-iops?orgId=1&panelId=2&from=now-1h&to=now&refresh=1m&var-Volume={{volume_name}}&var-SVM={{svm_name}}
```

#### Volume Detail Page — Throughput Panel

```
https://<amg-url>/d-solo/vol-throughput?orgId=1&panelId=3&from=now-1h&to=now&refresh=1m&var-Volume={{volume_name}}&var-SVM={{svm_name}}
```

#### Volume Detail Page — Latency Panel

```
https://<amg-url>/d-solo/vol-latency?orgId=1&panelId=4&from=now-1h&to=now&refresh=1m&var-Volume={{volume_name}}&var-SVM={{svm_name}}
```

#### SVM Overview — Aggregated Metrics

```
https://<amg-url>/d-solo/svm-overview?orgId=1&panelId=1&from=now-1h&to=now&refresh=1m&var-SVM={{svm_name}}
```

#### Dashboard Overview — Top Volumes

```
https://<amg-url>/d-solo/vol-top-n?orgId=1&panelId=1&from=now-1h&to=now&refresh=5m
```

### Authentication for Embedded Panels

Embedded panels share the same Cognito session as the ToolJet application because both are served through the same ALB domain:

1. User authenticates via Cognito (ALB authenticate action)
2. Session cookie is set for the ALB domain
3. ToolJet loads at `/app/*` with the session cookie
4. Embedded Grafana panels at `/grafana/*` share the same domain cookie
5. AMG validates the session and renders the panel

**No additional authentication configuration is needed** for embedded panels when using the ALB + Cognito pattern described in the architecture.

### Panel Embed URL Output File

After running `import-dashboards.sh`, the script generates `panel-embed-urls.json` containing all panel URLs:

```json
{
  "workspace_url": "https://<amg-workspace-url>",
  "generated_at": "2026-01-15T10:30:00Z",
  "embed_url_format": "<workspace_url>/d-solo/<dashboard_uid>?orgId=1&panelId=<panel_id>&from=now-1h&to=now&refresh=1m",
  "tooljet_iframe_template": "<iframe src=\"{embed_url}\" width=\"100%\" height=\"300\" frameborder=\"0\"></iframe>",
  "panels": [
    {
      "dashboard_title": "Volume Performance",
      "dashboard_uid": "fsxn-vol-perf",
      "panel_id": 2,
      "panel_title": "Volume IOPS",
      "embed_url": "https://<amg-workspace-url>/d-solo/fsxn-vol-perf?orgId=1&panelId=2&from=now-1h&to=now&refresh=1m",
      "iframe_html": "<iframe src=\"...\" width=\"100%\" height=\"300\" frameborder=\"0\"></iframe>"
    }
  ]
}
```

## Troubleshooting

### Dashboard shows "No data"

1. Verify Harvest is collecting metrics: check ECS task logs
2. Verify AMP data source is configured correctly in AMG
3. Check that the Prometheus query uses correct metric names
4. Verify template variables match your FSx ONTAP cluster/SVM names

### Panel embed returns 403

1. Verify the Cognito session cookie is valid
2. Check that the ALB listener rule for `/grafana/*` has Cognito auth action
3. Verify AMG workspace allows embedding (check workspace settings)

### Import script fails with "data source not found"

1. Ensure AMP workspace is deployed (`fsxn-mgmt-observability` stack)
2. Verify `--amp-workspace-id` parameter or stack output is correct
3. Check AMG workspace has permissions to query AMP (SigV4 auth)

## References

- [NetApp Harvest GitHub — Grafana Dashboards](https://github.com/NetApp/harvest/tree/main/grafana/dashboards)
- [AWS Docs — Amazon Managed Grafana](https://docs.aws.amazon.com/grafana/latest/userguide/what-is-Amazon-Managed-Service-Grafana.html)
- [AWS Docs — FSx ONTAP Monitoring](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-overview.html)
- [Grafana HTTP API — Dashboard](https://grafana.com/docs/grafana/latest/developers/http_api/dashboard/)
- [Grafana Embedding — Solo Panel](https://grafana.com/docs/grafana/latest/dashboards/share-dashboards-panels/#embed-a-panel)
