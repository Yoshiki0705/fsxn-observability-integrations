# Screenshots — Grafana E2E Verification

This directory contains screenshots captured during E2E verification of the Grafana Cloud Loki integration.

## Required Screenshots

| Filename | Description |
|----------|-------------|
| `explore-log-arrival.png` | Grafana Explore showing FSx for ONTAP audit log arrival with timestamp and content fields |
| `dashboard-overview.png` | Grafana dashboard with all 4 panels (log volume, operations breakdown, user activity, failure events) rendered with data |
| `grafana-ems-events.png` | Grafana Explore showing EMS events (`{service_name="fsxn-ems"}`) with event_name and severity fields |
| `grafana-fpolicy-events.png` | Grafana Explore showing FPolicy events (`{service_name="fsxn-fpolicy"}`) with operation and file_path fields |

## Capture Requirements

- **Format**: PNG
- **Minimum Resolution**: 1024×768 pixels
- **Content**: Each screenshot must clearly show the described UI elements with real data

---

## Capture Instructions

### `explore-log-arrival.png`

**Purpose**: Verify that FSx for ONTAP audit logs arrive in Grafana Cloud Loki and are queryable via Grafana Explore.

**Navigation Path**:

1. Log in to Grafana Cloud (`https://<instance>.grafana.net`)
2. Click the **Explore** icon (compass) in the left sidebar
3. Select **Loki** as the data source from the dropdown at the top
4. Set the time range to **"Last 15 minutes"** using the time picker in the top-right corner
5. Enter the following LogQL query in the query editor:
   ```
   {job="fsxn-audit"}
   ```
6. Click **Run query** (or press Shift+Enter)
7. Verify that at least 1 log entry is displayed with:
   - A visible timestamp
   - Log content fields (UserName, Operation, ObjectName)
8. Capture the screenshot at ≥1024×768 resolution

**Expected Visible Content**:
- Grafana Explore interface with Loki data source selected
- Query `{job="fsxn-audit"}` in the query editor
- At least 1 log entry in the results panel
- Timestamp column visible
- Structured log fields (UserName, Operation, ObjectName) visible in expanded log entry

---

### `dashboard-overview.png`

**Purpose**: Show the completed Grafana dashboard with all 4 monitoring panels rendering real data.

**Navigation Path**:

1. Log in to Grafana Cloud (`https://<instance>.grafana.net`)
2. Click the **Dashboards** icon (four squares) in the left sidebar
3. Navigate to the FSx for ONTAP audit log dashboard (or create it following the setup guide)
4. Ensure the time range covers a period with data (e.g., "Last 1 hour")
5. Verify all 4 panels are visible and rendering data:
   - **ログ量推移 (Log Volume)**: Time series panel showing `count_over_time({job="fsxn-audit"}[5m])`
   - **操作別内訳 (Operations Breakdown)**: Pie chart or bar gauge showing `sum by (Operation) (count_over_time({job="fsxn-audit"} | json [1h]))`
   - **ユーザーアクティビティ (User Activity)**: Table or bar gauge showing top 10 users by event count
   - **失敗イベント (Failure Events)**: Time series panel showing `count_over_time({job="fsxn-audit"} | json | Result="Failure" [5m])`
6. Capture the full dashboard at ≥1024×768 resolution

**Expected Visible Content**:
- Dashboard title visible
- All 4 panels rendered with data (no "No data" messages)
- Time series graphs showing data points over time
- Pie chart or bar gauge showing operation distribution
- User activity ranking visible
- Failure events panel (may show zero if no failures occurred — this is acceptable)

---

## Notes

- Screenshots are captured manually during E2E verification against real Grafana Cloud infrastructure
- Placeholder PNG files are committed initially and replaced with actual captures during verification
- Both the Japanese and English setup guides reference these screenshots via relative path `../screenshots/<filename>`
- EMS and FPolicy screenshots require Grafana Cloud login and data ingestion via OTLP Gateway

---

## EMS/FPolicy Screenshot Capture Instructions

### `grafana-ems-events.png`

**Purpose**: Verify that EMS events arrive in Grafana Cloud Loki and are queryable.

**Navigation Path**:

1. Log in to Grafana Cloud (`https://<instance>.grafana.net`)
2. Click the **Explore** icon (compass) in the left sidebar
3. Select **Loki** as the data source
4. Enter the following LogQL query:
   ```
   {service_name="fsxn-ems"}
   ```
5. Click **Run query**
6. Verify that EMS events are displayed with:
   - `event_name` field (e.g., `arw.volume.state`, `wafl.quota.softlimit.exceeded`)
   - `severity` field (e.g., `alert`, `warning`)
   - `svm` field
7. Capture the screenshot at ≥1024×768 resolution

---

### `grafana-fpolicy-events.png`

**Purpose**: Verify that FPolicy file operation events arrive in Grafana Cloud Loki.

**Navigation Path**:

1. Log in to Grafana Cloud (`https://<instance>.grafana.net`)
2. Click the **Explore** icon (compass) in the left sidebar
3. Select **Loki** as the data source
4. Enter the following LogQL query:
   ```
   {service_name="fsxn-fpolicy"}
   ```
5. Click **Run query**
6. Verify that FPolicy events are displayed with:
   - `operation` field (e.g., `create`, `write`, `rename`, `delete`)
   - `file_path` field
   - `user` field
   - `client_ip` field
7. Capture the screenshot at ≥1024×768 resolution

---

> **Note**: These placeholder PNG files (1x1 pixel) need to be replaced with actual Grafana UI captures after logging in and confirming data arrival. Run `python3 docs/screenshots/mask_screenshots.py` before committing actual screenshots.
