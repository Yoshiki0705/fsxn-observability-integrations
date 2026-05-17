# EMS/FPolicy Screenshot Capture Guide

## Capture Procedure

Capture the following screenshots and place them in `docs/screenshots/`.

---

### 1. Datadog: ARP Detection Log

**Filename**: `datadog-arp-detection.png`

**Steps**:
1. Navigate to https://ap1.datadoghq.com/logs
2. Enter `source:fsxn-ems` in the search bar
3. Set time range to "Past 1 Hour"
4. Confirm ARP events (`arw.volume.state`) are displayed
5. Capture screenshot with the log list visible

---

### 2. Datadog: ARP Log Detail

**Filename**: `datadog-arp-log-detail.png`

**Steps**:
1. Click on an ARP event from the search results above
2. The log detail panel expands
3. Expand the `attributes` section and confirm the following are visible:
   - `event_name`: `arw.volume.state`
   - `severity`: `alert`
   - `parameters.volume_name`: `vol_data`
   - `parameters.state`: `attack-detected`
4. Capture screenshot with structured attributes expanded

---

### 3. AWS CloudWatch: EMS Lambda Execution Logs

**Filename**: `aws-ems-lambda-logs.png`

**Steps**:
1. AWS Management Console → CloudWatch → Log groups
2. Select `/aws/lambda/fsxn-datadog-ems-fpolicy-ems`
3. Open the latest log stream
4. Confirm the following log messages are visible:
   - `EMS handler invoked: requestId=...`
   - `Parsed 1 EMS event(s)`
   - `Processing complete: {"message": "EMS events processed", "total_events": 1, "shipped": 1}`
5. Capture screenshot with log events visible

**Alternative**: You can use a terminal screenshot of AWS CLI output:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-ems-fpolicy-ems \
  --region ap-northeast-1 \
  --start-time $(($(date +%s) - 3600))000 \
  --limit 10
```

---

### 4. Datadog: FPolicy File Operation Log

**Filename**: `datadog-fpolicy-suspect-activity.png`

**Steps**:
1. Navigate to https://ap1.datadoghq.com/logs
2. Enter `source:fsxn-fpolicy` in the search bar
3. Set time range to "Past 1 Hour"
4. Confirm FPolicy events (file creation, etc.) are displayed
5. Capture screenshot with the log list visible

---

### 5. ONTAP CLI: ARP Status

**Filename**: `ontap-arp-status.png`

**Steps**:
1. SSH to the FSx ONTAP management endpoint:
   ```bash
   ssh admin@management.fs-09ffe72a3b2b7dbbd.fsx.ap-northeast-1.amazonaws.com
   ```
2. Execute the following command:
   ```
   security anti-ransomware volume show
   ```
3. Capture screenshot of the output

---

### 6. ONTAP CLI: ARP Snapshot List

**Filename**: `ontap-arp-snapshot.png`

**Steps**:
1. SSH to the FSx ONTAP management endpoint (same as above)
2. Execute the following command:
   ```
   volume snapshot show -snapshot Anti_ransomware*
   ```
3. Capture screenshot of the output

---

## Destination Directory

Place all screenshots in the following directory:

```
docs/screenshots/
├── datadog-arp-detection.png
├── datadog-arp-log-detail.png
├── aws-ems-lambda-logs.png
├── datadog-fpolicy-suspect-activity.png
├── ontap-arp-status.png
└── ontap-arp-snapshot.png
```

## Capture Tips

- **Resolution**: Minimum 1280x720
- **Format**: PNG
- **Privacy**: Ensure no API keys or passwords are visible
- **Timestamps**: Capture with log timestamps visible
- **Structured Attributes**: In Datadog log detail, capture with attributes expanded
