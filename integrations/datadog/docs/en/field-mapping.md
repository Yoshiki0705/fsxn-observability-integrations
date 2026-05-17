# Datadog Field Mapping

## Event Sources and Tags

| Source | `source` tag | `service` tag | Trigger |
|--------|-------------|---------------|---------|
| File Access Audit Logs | `fsxn` | `fsxn-ontap` | EventBridge Scheduler |
| EMS Webhooks | `fsxn-ems` | `fsxn-ontap` | API Gateway |
| FPolicy Events | `fsxn-fpolicy` | `fsxn-ontap` | SQS → Lambda |

## File Access Audit Log Attributes

| Datadog Attribute | ONTAP Source (EVTX) | ONTAP Source (XML) | Description |
|-------------------|--------------------|--------------------|-------------|
| `attributes.svm` | SVMName | Computer | Storage Virtual Machine name |
| `attributes.user` | UserName | SubjectUserName | User who performed the operation |
| `attributes.client_ip` | ClientIP | IpAddress | Client IP address |
| `attributes.operation` | Operation | ObjectType | Operation type (ReadData, WriteData, etc.) |
| `attributes.path` | ObjectName | ObjectName | File/directory path |
| `attributes.result` | Result | Keywords | Success or Failure |
| `attributes.event_type` | EventID | EventID | Windows Event ID (4663, 4656, etc.) |
| `host` | — | — | Set to ONTAP node name |
| `timestamp` | Record timestamp | TimeCreated SystemTime | Event timestamp (ISO 8601) |

## EMS Event Attributes

| Datadog Attribute | EMS Field | Description |
|-------------------|-----------|-------------|
| `attributes.event_name` | messageName | EMS event name (e.g., `arw.volume.state`) |
| `attributes.severity` | severity | Event severity (alert, error, warning, info) |
| `attributes.source_node` | node | ONTAP node that generated the event |
| `attributes.svm` | svmName | SVM name |
| `attributes.parameters.*` | parameters.* | Event-specific parameters |
| `host` | node | ONTAP node name |
| `message` | message | Human-readable event description |

### ARP (Anti-Ransomware) Event Example

```json
{
  "source": "fsxn-ems",
  "service": "fsxn-ontap",
  "host": "fsxn-node-01",
  "message": "Anti-ransomware: Volume vol_data state changed to attack-detected",
  "attributes": {
    "event_name": "arw.volume.state",
    "severity": "alert",
    "source_node": "fsxn-node-01",
    "svm": "svm-prod-01",
    "parameters": {
      "volume_name": "vol_data",
      "state": "attack-detected"
    }
  }
}
```

## FPolicy Event Attributes

| Datadog Attribute | FPolicy Field | Description |
|-------------------|--------------|-------------|
| `attributes.operation` | operation | File operation (create, write, delete, rename, open) |
| `attributes.file_path` | file_path | Full file path |
| `attributes.user` | user | User identity |
| `attributes.client_ip` | client_ip | Client IP address |
| `attributes.vserver` | vserver | SVM (vserver) name |
| `attributes.protocol` | protocol | Access protocol (cifs, nfs) |
| `host` | vserver | SVM name |
| `message` | — | Formatted: `FPolicy: <op> <path> by <user> from <ip>` |

## Datadog Search Queries

| Use Case | Query |
|----------|-------|
| All FSx ONTAP audit logs | `source:fsxn` |
| Failed access attempts | `source:fsxn @attributes.result:Failure` |
| ARP ransomware alerts | `source:fsxn-ems @attributes.event_name:arw.volume.state` |
| FPolicy file operations | `source:fsxn-fpolicy` |
| Specific user activity | `source:fsxn @attributes.user:admin@corp.local` |
| Specific file path | `source:fsxn @attributes.path:"/vol/data/confidential/*"` |

## Datadog Monitor Examples

### ARP Ransomware Detection

```json
{
  "name": "FSx ONTAP: Ransomware Detected (ARP)",
  "type": "log alert",
  "query": "source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.parameters.state:attack-detected",
  "message": "🚨 ONTAP Anti-Ransomware Protection detected encryption activity.\n\nVolume: {{attributes.parameters.volume_name}}\nSVM: {{attributes.svm}}\nNode: {{host}}\n\nImmediate actions:\n1. Create snapshot of affected volume\n2. Disable client access\n3. Investigate with FPolicy logs",
  "options": {
    "thresholds": {"critical": 0},
    "notify_no_data": false
  }
}
```

### Bulk Failed Access

```json
{
  "name": "FSx ONTAP: Bulk Failed Access Attempts",
  "type": "log alert",
  "query": "source:fsxn @attributes.result:Failure",
  "message": "⚠️ Multiple failed file access attempts detected.\n\nUser: {{attributes.user}}\nClient IP: {{attributes.client_ip}}\n\nThis may indicate unauthorized access attempts.",
  "options": {
    "thresholds": {"critical": 10, "warning": 5},
    "timeframe": "5m"
  }
}
```
