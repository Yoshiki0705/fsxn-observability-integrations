# SPL vs CQL Query Comparison — FSxN Audit Logs

For SOC analysts working across Splunk and CrowdStrike LogScale, this table maps common FSxN audit log queries between SPL and CQL.

## Query Comparison Table

| Operation | Splunk SPL | LogScale CQL |
|-----------|-----------|--------------|
| **Time bucket (5 min)** | `\| bin _time span=5m` | `\| bucket(span=5m)` |
| **Top 10 users** | `\| top limit=10 user` | `\| top(user, limit=10)` |
| **Count by user** | `\| stats count by user` | `\| groupBy(user, function=count())` |
| **Filter + aggregate** | `source="fsxn" event_type=4660 \| stats count by user` | `#repo=fsxn_audit event_type="4660" \| groupBy(user, function=count())` |
| **Time range** | `earliest=-1h latest=now` | Query time picker or `@timestamp > now() - 1h` |
| **String match (wildcard)** | `path="*finance*"` | `path = /share/finance/*` (glob) |
| **Exclude pattern** | `NOT user="svc-*"` | `user != "svc-*"` |
| **Unique values** | `\| stats dc(user) as unique_users` | `\| count(user, distinct=true)` |

## Detection Query Examples

### Mass File Deletion

**Splunk SPL:**
```spl
index=fsxn_audit sourcetype=fsxn:audit:xml event_type=4660
| bin _time span=5m
| stats count by _time, user, client_ip
| where count > 50
| sort - count
```

**LogScale CQL:**
```
#repo=fsxn_audit event_type="4660"
| bucket(span=5m)
| groupBy([_bucket, user, client_ip], function=count())
| _count > 50
| sort(_count, order=desc)
```

### After-Hours Access

**Splunk SPL:**
```spl
index=fsxn_audit sourcetype=fsxn:audit:xml
| eval hour=strftime(_time, "%H")
| where hour > "19" OR hour < "07"
| stats count by user, path
| sort - count
```

**LogScale CQL:**
```
#repo=fsxn_audit
| parseTimestamp(field=timestamp, format="yyyy-MM-dd'T'HH:mm:ss")
| hour := formatTime(field=@timestamp, format="HH")
| hour > "19" OR hour < "07"
| groupBy([user, path], function=count())
| sort(_count, order=desc)
```

## Key Differences

| Aspect | SPL | CQL |
|--------|-----|-----|
| Repository/Index | `index=fsxn_audit` | `#repo=fsxn_audit` |
| Pipe model | Sequential transformation | Similar (different function names) |
| Time field | `_time` (automatic) | `@timestamp` (automatic) |
| Case sensitivity | Case-insensitive by default | Case-sensitive |

## Normalized Field Schema

Both platforms use the same field names from the FSxN parser:

| Field | Description | Example |
|-------|-------------|---------|
| `user` | Windows domain user | `CORP\user-finance-01` |
| `path` | File/directory path | `/share/finance/report.xlsx` |
| `client_ip` | Source workstation IP | `10.0.x.x` |
| `event_type` | Windows EventID | `4660` |
| `result` | Audit outcome | `Audit Success` / `Audit Failure` |
| `svm` | Storage Virtual Machine | `ProductionSVM` |
| `operation` | Operation type | `File` |
| `timestamp` | Event time (ISO 8601) | `2026-06-14T12:13:00.000000Z` |

---

## Related Documents

- [Production Checklist](production-checklist.md)
- [Setup Guide](setup-guide.md)
- [Field Mapping](field-mapping.md)
- [README (main)](../../README.md)
- [CrowdStrike LogScale Integration](../../../crowdstrike/README.md)
- [Splunk Integration](../../../splunk-serverless/README.md)
