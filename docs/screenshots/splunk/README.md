# Splunk E2E Verification Screenshots

This directory stores screenshot evidence for the Splunk serverless integration E2E verification.

## Required Screenshots

The following 3 PNG screenshots are required to complete E2E verification:

### 1. Lambda CloudWatch Logs

- **Filename**: `splunk-lambda-cloudwatch-<YYYYMMDD>.png`
- **Content**: Lambda CloudWatch Logs showing a log line containing the text "Successfully shipped" with a visible timestamp
- **Purpose**: Confirms the Lambda shipper executed successfully and delivered logs to Splunk HEC

### 2. Splunk Search Results

- **Filename**: `splunk-search-results-<YYYYMMDD>.png`
- **Content**: Splunk Search results showing log entries with visible `index`, `sourcetype`, `host`, and `source` fields
- **SPL Query**: `index=fsxn_audit sourcetype=fsxn:ontap:audit earliest=-15m`
- **Purpose**: Confirms logs arrived in Splunk and are searchable with correct field mappings

### 3. Splunk Dashboard

- **Filename**: `splunk-dashboard-<YYYYMMDD>.png`
- **Content**: Splunk dashboard visualization showing at least one panel with FSx for ONTAP audit log data
- **Purpose**: Demonstrates operational visibility into FSx for ONTAP audit events via Splunk

## Naming Convention

All screenshot files MUST follow this pattern:

```
splunk-<description>-<YYYYMMDD>.png
```

Where:
- `splunk-` — fixed prefix
- `<description>` — 3 to 40 characters, lowercase alphanumeric and hyphens only (`[a-z0-9-]{3,40}`)
- `<YYYYMMDD>` — capture date in ISO format (e.g., `20260115`)
- `.png` — PNG format only

### Valid Examples

```
splunk-lambda-cloudwatch-20260115.png
splunk-search-results-20260115.png
splunk-dashboard-20260115.png
splunk-ems-arp-detection-20260120.png
splunk-fpolicy-file-ops-20260120.png
```

### Invalid Examples

```
splunk-Lambda-CloudWatch-20260115.png   # uppercase not allowed
splunk-ab-20260115.png                  # description too short (< 3 chars)
splunk-search-results-20260115.jpg      # wrong extension
screenshot-splunk-20260115.png          # wrong prefix
```

## File Size Limits

- **Maximum**: 500 KB per screenshot
- **Format**: PNG only (must start with PNG magic bytes `\x89PNG\r\n\x1a\n`)

## Capture Guidelines

1. **Resolution**: Use a resolution that makes text clearly readable
2. **Sensitive data**: Mask or redact any sensitive information (API keys, internal hostnames) before committing
3. **Timestamps**: Ensure timestamps are visible in the screenshot to correlate with verification timing
4. **Fields**: For Splunk Search screenshots, expand at least one event to show structured field values

## Directory Structure

```
docs/screenshots/splunk/
├── .gitkeep                              # Ensures directory is tracked in git
├── README.md                             # This file
├── splunk-lambda-cloudwatch-YYYYMMDD.png # Required: Lambda success log
├── splunk-search-results-YYYYMMDD.png    # Required: Splunk search results
└── splunk-dashboard-YYYYMMDD.png         # Required: Splunk dashboard
```

## Referencing Screenshots

From setup guides, reference screenshots using relative paths:

```markdown
<!-- From integrations/splunk-serverless/docs/ja/setup-guide.md -->
![Splunk Search Results](../../../docs/screenshots/splunk/splunk-search-results-YYYYMMDD.png)

<!-- From integrations/splunk-serverless/docs/en/setup-guide.md -->
![Splunk Search Results](../../../docs/screenshots/splunk/splunk-search-results-YYYYMMDD.png)
```
