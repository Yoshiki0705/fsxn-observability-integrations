# Detection Use Cases

## Event Source Selection Matrix

| Detection Use Case | Best Source | Why | Latency |
|-------------------|-------------|-----|---------|
| Ransomware encryption behavior | EMS (ARP) | ONTAP native ML-based detection | Real-time (webhook) |
| Bulk file deletion | Audit Logs or FPolicy | Audit for near-real-time, FPolicy for real-time | Minutes / Seconds |
| Unusual read volume | Audit Logs | Policy-dependent, volume-heavy | Minutes |
| Unauthorized access attempts | Audit Logs | Failed access events (Result: Failure) | Minutes |
| Real-time file blocking / DLP | FPolicy | Protocol-level interception | Sub-second |
| Quota threshold exceeded | EMS | ONTAP native quota monitoring | Real-time (webhook) |
| Suspicious user behavior | FPolicy + Audit Logs | Correlate real-time ops with historical pattern | Seconds + Minutes |
| Permission changes | Audit Logs | SACL/ACL modification events | Minutes |

## Source Characteristics

| Source | Latency Model | Volume | Best For |
|--------|--------------|--------|----------|
| File Access Audit Logs | Near-real-time (Scheduler frequency + rotation interval) | High (especially with read auditing) | Compliance, forensics, pattern analysis |
| EMS Webhooks | Real-time (HTTPS push) | Low (critical events only) | Security alerting, operational monitoring |
| FPolicy | Real-time (TCP stream) | Medium-High (all file operations) | DLP, real-time monitoring, suspicious behavior |

## Datadog Monitor Examples by Use Case

### Ransomware Detection (ARP + EMS)

```
Query: source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.parameters.state:attack-detected
Threshold: critical > 0
Action: PagerDuty + Slack + snapshot affected volume
```

### Bulk Failed Access (Audit Logs)

```
Query: source:fsxn @attributes.result:Failure
Threshold: critical > 10 in 5 minutes
Action: Investigate user + client IP
```

### Unusual File Deletion Rate (FPolicy)

```
Query: source:fsxn-fpolicy @attributes.operation:delete
Threshold: warning > 50 in 5 minutes, critical > 200 in 5 minutes
Action: Correlate with user identity
```

### Sensitive Path Access (Audit Logs)

```
Query: source:fsxn @attributes.path:"/vol/data/confidential/*"
Threshold: warning > 0 (any access to sensitive path)
Action: Log review + user verification
```

## Correlation Patterns

For advanced detection, correlate across sources:

1. **ARP alert + FPolicy bulk operations** — Confirms ransomware activity with file-level detail
2. **Failed access spike + successful access from new IP** — Potential credential compromise
3. **Quota warning + bulk write from single user** — Possible data exfiltration or abuse
