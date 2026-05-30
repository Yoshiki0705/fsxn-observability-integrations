# ToolJet Workflow Exports

Pre-built ToolJet workflow JSON files for FSx for ONTAP management operations. These workflows provide a complete storage management UI when imported into ToolJet.

## Workflows

| File | Description | ONTAP REST API Endpoints |
|------|-------------|--------------------------|
| `volume-management.json` | Volume CRUD (create, list, resize, delete with confirmation) | `/api/storage/volumes`, `/api/storage/aggregates`, `/api/svm/svms` |
| `svm-management.json` | SVM list, detail view, DNS configuration, export policies | `/api/svm/svms`, `/api/network/ip/interfaces`, `/api/name-services/dns`, `/api/protocols/nfs/export-policies` |
| `snapshot-management.json` | Snapshot CRUD and restore operations | `/api/storage/volumes/{uuid}/snapshots` |
| `replication-management.json` | SnapMirror relationship management with transfer progress polling | `/api/snapmirror/relationships`, `/api/snapmirror/relationships/{uuid}/transfers` |
| `s3-file-browser.json` | S3 Access Point file browser with Lambda-based download | Lambda invocation (copy-to-bucket + presigned URL) |

## Prerequisites

Before importing these workflows, ensure:

1. **ToolJet is deployed** via the `fsxn-mgmt-console` CloudFormation stack
2. **ONTAP credentials** are stored in AWS Secrets Manager
3. **Global variables** are configured in ToolJet (see below)

## Required Global Variables

Configure these in ToolJet Settings → Global Variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `ontap_base_url` | FSx for ONTAP management endpoint (HTTPS) | `https://<management-ip>` |
| `ontap_username` | ONTAP admin username | `fsxadmin` |
| `ontap_password` | ONTAP admin password | (from Secrets Manager) |
| `lambda_invoke_url` | S3 Copy Lambda invoke URL | (from CloudFormation stack output) |
| `s3_access_point_arn` | FSx for ONTAP S3 Access Point ARN | `arn:aws:s3:<region>:123456789012:accesspoint/<name>` |

## Import Instructions

### Method 1: ToolJet UI Import

1. Log in to ToolJet at `https://<alb-dns>/app`
2. Navigate to **Apps** → **Import**
3. Select the JSON file to import
4. Repeat for each workflow file
5. Configure the data source credentials after import

### Method 2: ToolJet CLI Import

```bash
# Install ToolJet CLI
npm install -g @tooljet/cli

# Set ToolJet host
export TOOLJET_HOST="https://<alb-dns>"
export TOOLJET_TOKEN="<your-api-token>"

# Import each workflow
tooljet app import --file volume-management.json
tooljet app import --file svm-management.json
tooljet app import --file snapshot-management.json
tooljet app import --file replication-management.json
tooljet app import --file s3-file-browser.json
```

### Method 3: Init Script (Automated First Boot)

The deployment script can automatically import workflows on first boot:

```bash
# In the ToolJet ECS task definition, add an init container or startup script:
for workflow in /opt/tooljet-workflows/*.json; do
  tooljet app import --file "$workflow" --skip-existing
done
```

## Data Source Configuration

After importing, configure the ONTAP REST API data source:

1. Go to **Data Sources** → **FSxN ONTAP REST**
2. Set the base URL to your FSx for ONTAP management endpoint
3. Configure Basic Auth with credentials from Secrets Manager
4. Test the connection

### Authentication

The workflows use Basic Authentication against the ONTAP REST API:
- Username: `{{globals.ontap_username}}`
- Password: `{{globals.ontap_password}}`

For production, store credentials in ToolJet's encrypted credential store backed by the RDS PostgreSQL database.

## Workflow Features

### Volume Management
- **Create**: Form with validation (name: 1-203 chars alphanumeric/underscore, size: 20 MB - 100 TB)
- **List**: Table with used capacity, percentage, state, SVM association
- **Resize**: Modal with size validation
- **Delete**: Confirmation dialog → offline → delete sequence

### SVM Management
- **List**: Table with state indicators (warning for non-running SVMs)
- **Detail**: Network interfaces, DNS settings, export policies
- **Configure**: DNS domain/server modification

### Snapshot Management
- **Create**: Name validation (1-255 chars, alphanumeric/hyphen/underscore)
- **List**: Sorted by creation time descending, paginated at 50 per page
- **Delete**: Confirmation showing snapshot name, volume, and creation time
- **Restore**: Confirmation with data loss warning

### Replication Management
- **List**: SnapMirror relationships with state, lag time, transfer info
- **Update**: Trigger replication transfer with 10-second progress polling
- **Resync**: One-click resync for broken-off relationships
- **Break**: Confirmation dialog for breaking relationships

### S3 File Browser
- **Browse**: Prefix-based navigation with folder/file separation
- **Metadata**: File size, last modified, content type, storage class
- **Download**: Lambda-based copy-to-bucket + presigned URL (3600s expiry)
- **Limits**: 5 GB max file size, 1000 objects per page

## Validation Rules

All workflows include client-side validation:

| Field | Rule | Error Message |
|-------|------|---------------|
| Volume Name | `^[a-zA-Z0-9_]{1,203}$` | Must be 1-203 characters, alphanumeric and underscores only |
| Volume Size | 1 - 107374 GB | Must be between 20 MB and 100 TB |
| Junction Path | `^/[a-zA-Z0-9_/\-]+$` | Must start with / |
| Snapshot Name | `^[a-zA-Z0-9_\-]{1,255}$` | Must be 1-255 characters, alphanumeric, hyphens, and underscores only |

## Error Handling

All workflows implement consistent error handling:

- **ONTAP API errors**: Display error code and message from API response
- **Network timeouts** (30s): Display "service unavailable" message
- **Validation failures**: Field-level error messages, API call prevented
- **Destructive operations**: Confirmation dialog required before execution

## Customization

To modify workflows after import:

1. Open the app in ToolJet editor
2. Modify queries, components, or event handlers as needed
3. Add additional Grafana panel embeds for inline metrics
4. Customize table columns or form fields

### Adding Grafana Panel Embeds

To embed Grafana panels alongside volume/SVM data:

```
Component: iframe
URL: {{globals.grafana_url}}/d-solo/<dashboard-uid>/<dashboard-name>?orgId=1&panelId=<panel-id>&var-volume={{variables.selectedVolumeName}}&from=now-1h&to=now
```
