# Demo Scenarios

## Overview

Demo procedures and scenarios for each vendor integration. Use these during actual demo sessions.

---

## Scenario 1: Unauthorized Access Detection (Datadog)

### Story
Detect unauthorized access attempts to confidential files and trigger real-time alerts in Datadog.

### Steps

1. **Setup**: Datadog integration deployed
2. **Action**: Access a restricted file on the FSx for ONTAP mount point without permission
   ```bash
   # Attempt to access a confidential file as an unauthorized user
   sudo -u testuser cat /mnt/fsxn/confidential/secret-report.pdf
   # → Permission denied (recorded as Failure in audit log)
   ```
3. **Verify**: Check in Datadog Logs
   - Search: `source:fsxn @attributes.result:Failure`
   - Confirm spike in failed access on the dashboard
4. **Alert**: Datadog Monitor triggers Slack/PagerDuty notification on threshold breach

### Expected Result
- Event arrives in Datadog within 30 seconds
- Traceable by `@attributes.user`, `@attributes.path`, `@attributes.client_ip`

---

## Scenario 2: Ransomware Detection (Splunk + EMS)

### Story
ARP/AI detects ransomware-like activity and sends alert to Splunk via EMS event.

### Steps

1. **Setup**: Splunk integration + EMS webhook configured
2. **Simulate**: Execute mass file rename operations
   ```bash
   # Simulate ransomware-like mass rename (test environment only)
   for f in /mnt/fsxn/test-data/*.txt; do
     mv "$f" "${f}.encrypted"
   done
   ```
3. **ARP Detection**: ONTAP ARP/AI detects the anomaly
   - EMS event `arw.volume.state` is emitted
   - Automatic snapshot `Anti_ransomware_backup_*` is created
4. **Splunk Verification**:
   - Search: `index=fsxn_audit sourcetype=fsxn:ontap:audit event_type=arw*`
   - Alert: Confirm on "ARP Detection" dashboard

### Expected Result
- Alert arrives in Splunk within 1 minute of ARP detection
- Attack timeline visualized in Splunk dashboard

---

## Scenario 3: Quota Threshold Alert (New Relic + EMS)

### Story
User storage exceeds soft quota, admin notified via New Relic.

### Steps

1. **Setup**: New Relic integration + EMS CloudWatch integration configured
2. **Action**: Write a large file to exceed quota
   ```bash
   # Create a large test file
   dd if=/dev/zero of=/mnt/fsxn/user-data/large-file.bin bs=1M count=500
   ```
3. **EMS Emission**: `wafl.quota.softlimit.exceeded` event fires
4. **New Relic Verification**:
   - Filter in Logs UI: `source:fsxn-ontap`
   - NRQL: `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND event_type LIKE 'wafl.quota%' SINCE 1 hour ago`

### Expected Result
- Log arrives in New Relic within 2 minutes of quota breach
- Automatic notification via New Relic Alert Condition

---

## Scenario 4: Multi-Vendor Fan-Out (OTel Collector)

### Story
Ship same audit logs to Grafana Cloud and Honeycomb simultaneously via OTel Collector.

### Steps

1. **Setup**: OTel Collector integration deployed + Collector configured
   ```yaml
   # otel-collector-config.yaml (verified working)
   exporters:
     otlp_http/grafana:
       endpoint: https://otlp-gateway-prod-ap-southeast-0.grafana.net/otlp
       headers:
         Authorization: Basic ${GRAFANA_BASIC_AUTH}
     otlp_http/honeycomb:
       endpoint: https://api.honeycomb.io
       headers:
         x-honeycomb-team: ${HONEYCOMB_KEY}
         x-honeycomb-dataset: fsxn-audit
   service:
     pipelines:
       logs:
         exporters: [otlp_http/grafana, otlp_http/honeycomb]
   ```
2. **Action**: Perform file operations on FSx for ONTAP
3. **Verify**:
   - Grafana: Explore → Loki → `{job="fsxn-audit"}`
   - Honeycomb: Dataset `fsxn-audit` → Query

### Expected Result
- Identical events arrive at both vendors
- No code changes required when switching vendors

---

## Scenario 5: Compliance Audit Report (Elastic)

### Story
Generate quarterly compliance report from Elasticsearch audit log indices.

### Steps

1. **Setup**: Elastic integration deployed
2. **Data Accumulation**: Audit logs accumulate in daily indices during normal operation
3. **Report Generation**: Visualize in Kibana
   ```
   GET fsxn-audit-2026.01.*/_search
   {
     "query": {"bool": {"must": [
       {"term": {"fsxn.svm": "svm-prod-01"}},
       {"range": {"@timestamp": {"gte": "2026-01-01", "lte": "2026-03-31"}}}
     ]}},
     "aggs": {
       "by_user": {"terms": {"field": "user.name.keyword"}},
       "by_operation": {"terms": {"field": "fsxn.operation.keyword"}}
     }
   }
   ```
4. **Dashboard**: Visualize access patterns in Kibana Dashboard

---

## Scenario 6: FPolicy Real-Time File Monitoring (Dynatrace)

### Story
Alert immediately when files with specific extensions (.exe, .bat, .ps1) are created.

### Steps

1. **Setup**: FPolicy + Dynatrace integration configured
2. **FPolicy Configuration**:
   ```bash
   fpolicy policy event create -vserver svm-prod-01 \
     -event-name suspicious-files \
     -protocol cifs \
     -file-operations create \
     -filters-on-extension exe,bat,ps1,vbs
   ```
3. **Action**: Create a suspicious file
   ```bash
   echo "test" > /mnt/fsxn/shared/malware.exe
   ```
4. **Dynatrace Verification**: Problems → Custom events

---

## Demo Environment Checklist

- [ ] FSx for ONTAP file system running
- [ ] Audit logging enabled
- [ ] S3 bucket + Access Point deployed
- [ ] Target vendor integration stack deployed
- [ ] Test files/directories prepared
- [ ] Vendor-side dashboard/alerts configured
- [ ] Screenshot capture tools ready

## Screenshot Capture Points

Capture the following screenshots for each demo:

1. **Lambda CloudWatch Logs**: Successful processing logs
2. **Vendor UI**: Log arrival confirmation screen
3. **Dashboard**: Visualized data
4. **Alert**: Notification fired screen
5. **Architecture Diagram**: Actual resource layout
