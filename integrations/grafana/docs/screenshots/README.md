# Screenshots — Grafana E2E Verification

This directory contains screenshots captured during E2E verification of the Grafana Cloud Loki integration.

## Required Screenshots

| Filename | Description |
|----------|-------------|
| `explore-log-arrival.png` | Grafana Explore showing FSxN audit log arrival with timestamp and content fields |
| `dashboard-overview.png` | Grafana dashboard with all 4 panels (log volume, operations breakdown, user activity, failure events) rendered with data |

## Capture Requirements

- **Format**: PNG
- **Minimum Resolution**: 1024×768 pixels
- **Content**: Each screenshot must clearly show the described UI elements with real data

---

## Capture Instructions

### `explore-log-arrival.png`

**Purpose**: Verify that FSxN audit logs arrive in Grafana Cloud Loki and are queryable via Grafana Explore.

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
3. Navigate to the FSxN audit log dashboard (or create it following the setup guide)
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
