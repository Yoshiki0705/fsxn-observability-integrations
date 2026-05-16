# Demo Scenarios

## Overview

Demo procedures and scenarios for each vendor integration.

---

## Scenario 1: Unauthorized Access Detection (Datadog)

### Story
Detect unauthorized access attempts to confidential files and trigger real-time alerts in Datadog.

### Steps
1. **Setup**: Datadog integration deployed
2. **Action**: Access a restricted file without permission
   ```bash
   sudo -u testuser cat /mnt/fsxn/confidential/secret-report.pdf
   ```
3. **Verify**: Datadog Logs → `source:fsxn @attributes.result:Failure`
4. **Alert**: Datadog Monitor triggers Slack/PagerDuty notification

### Expected Result
- Event arrives in Datadog within 30 seconds
- Traceable by user, path, and client IP

---

## Scenario 2: Ransomware Detection (Splunk + EMS)

### Story
ARP/AI detects ransomware-like activity and sends alert to Splunk via EMS webhook.

### Steps
1. **Setup**: Splunk integration + EMS webhook configured
2. **Simulate**: Mass file rename operations
   ```bash
   for f in /mnt/fsxn/test-data/*.txt; do mv "$f" "${f}.encrypted"; done
   ```
3. **ARP Detection**: EMS event `arw.volume.state` fires
4. **Splunk**: Search `index=fsxn_audit event_type=arw*`

### Expected Result
- Alert in Splunk within 1 minute of ARP detection
- Attack timeline visible in dashboard

---

## Scenario 3: Quota Threshold Alert (New Relic + EMS)

### Story
User storage exceeds soft quota, admin notified via New Relic.

### Steps
1. **Setup**: New Relic + EMS CloudWatch integration
2. **Action**: Write large file to exceed quota
   ```bash
   dd if=/dev/zero of=/mnt/fsxn/user-data/large-file.bin bs=1M count=500
   ```
3. **EMS**: `wafl.quota.softlimit.exceeded` event fires
4. **New Relic**: NRQL query for quota events

---

## Scenario 4: Multi-Vendor Fan-Out (OTel Collector)

### Story
Ship same audit logs to Grafana Cloud and Honeycomb simultaneously via OTel Collector.

### Steps
1. **Setup**: OTel integration with multi-exporter collector config
2. **Action**: File operations on FSx ONTAP
3. **Verify**: Both Grafana and Honeycomb receive identical events

---

## Scenario 5: Compliance Audit Report (Elastic)

### Story
Generate quarterly compliance report from Elasticsearch audit log indices.

### Steps
1. **Setup**: Elastic integration with daily indices
2. **Query**: Kibana aggregation by user and operation
3. **Dashboard**: Visualize access patterns

---

## Scenario 6: FPolicy Real-Time File Monitoring (Dynatrace)

### Story
Alert on suspicious file extensions (.exe, .bat, .ps1) created on file shares.

### Steps
1. **Setup**: FPolicy + Dynatrace integration
2. **Action**: Create suspicious file
   ```bash
   echo "test" > /mnt/fsxn/shared/malware.exe
   ```
3. **Dynatrace**: Custom event alert fires

---

## Demo Environment Checklist

- [ ] FSx ONTAP file system running
- [ ] Audit logging enabled
- [ ] S3 bucket + Access Point deployed
- [ ] Target vendor integration stack deployed
- [ ] Test files/directories prepared
- [ ] Vendor-side dashboard/alerts configured
- [ ] Screenshot tools ready

## Screenshot Capture Points

1. Lambda CloudWatch Logs (successful processing)
2. Vendor UI (log arrival confirmation)
3. Dashboard (visualized data)
4. Alert (notification fired)
5. Architecture diagram (actual resource layout)
