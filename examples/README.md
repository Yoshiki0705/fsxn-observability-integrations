# Sample Payloads

> ⚠️ **Synthetic Test Data Only**: All payloads in this directory are synthetic (fabricated) test data. They do not contain real user identities, file paths, IP addresses, or any production data. Do NOT replace these with real audit logs — use them only for pipeline validation and testing.

Pre-built sample events for testing FSx for ONTAP observability integrations without real infrastructure.

## Usage

These payloads can be used to:
- Validate Lambda handler parsing logic
- Test OTLP / HEC / vendor-specific formatting
- Verify backend delivery and field mapping
- Run unit tests and integration tests

## Directory Structure

```
examples/
├── audit/              # FSx ONTAP audit log samples
│   └── sample-audit-log.json
├── ems/                # EMS webhook event samples
│   ├── sample-ransomware-event.json
│   └── sample-quota-exceeded-event.json
└── fpolicy/            # FPolicy file operation samples
    ├── sample-file-create-event.json
    └── sample-file-delete-event.json
```

## Testing with Sample Data

```bash
# Test audit log handler locally
cd integrations/datadog
python -c "
import json
from lambda.handler import _parse_audit_logs
with open('../../examples/audit/sample-audit-log.json') as f:
    logs = json.load(f)
print(json.dumps(logs, indent=2))
"

# Generate dynamic payloads with current timestamps
bash scripts/generate-splunk-hec-payload.sh --count 5
bash scripts/generate-otlp-payload.sh --count 5
```

## Notes

- Timestamps in these files are static examples. For testing with backends that reject old timestamps, use the `scripts/generate-*-payload.sh` scripts which generate current timestamps.
- All resource IDs and IP addresses are placeholders.
- These payloads match the normalized event schema documented in `docs/en/normalized-event-schema.md`.
