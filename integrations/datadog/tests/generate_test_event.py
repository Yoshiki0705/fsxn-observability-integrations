#!/usr/bin/env python3
"""Generate test audit log data with current timestamps.

Creates a JSON file with FSx ONTAP audit log entries using the current
timestamp, suitable for Lambda invocation testing where Datadog requires
recent timestamps for log indexing.

Usage:
    python3 integrations/datadog/tests/generate_test_event.py \
        --output /tmp/current_audit_logs.json \
        --bucket fsxn-audit-logs-observability-test
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


SAMPLE_EVENTS = [
    {
        "EventID": "4663",
        "SVMName": "svm-prod-01",
        "UserName": "admin@corp.local",
        "ClientIP": "10.0.1.50",
        "Operation": "ReadData",
        "ObjectName": "/vol/data/reports/quarterly.xlsx",
        "Result": "Success",
    },
    {
        "EventID": "4663",
        "SVMName": "svm-prod-01",
        "UserName": "user1@corp.local",
        "ClientIP": "10.0.1.51",
        "Operation": "WriteData",
        "ObjectName": "/vol/data/shared/document.docx",
        "Result": "Success",
    },
    {
        "EventID": "4656",
        "SVMName": "svm-prod-01",
        "UserName": "unknown@external.com",
        "ClientIP": "192.168.1.100",
        "Operation": "Open",
        "ObjectName": "/vol/data/confidential/secret.pdf",
        "Result": "Failure",
    },
    {
        "EventID": "4670",
        "SVMName": "svm-prod-01",
        "UserName": "admin@corp.local",
        "ClientIP": "10.0.1.50",
        "Operation": "SetSecurityDescriptor",
        "ObjectName": "/vol/data/shared/",
        "Result": "Success",
    },
    {
        "EventID": "4663",
        "SVMName": "svm-prod-01",
        "UserName": "service-account@corp.local",
        "ClientIP": "10.0.2.10",
        "Operation": "ReadData",
        "ObjectName": "/vol/data/backups/daily-backup.tar.gz",
        "Result": "Success",
    },
]


def generate_audit_logs() -> str:
    """Generate newline-delimited JSON audit logs with current timestamp."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    for event in SAMPLE_EVENTS:
        entry = {"timestamp": now, **event}
        lines.append(json.dumps(entry))
    return "\n".join(lines) + "\n"


def generate_s3_event(bucket: str, key: str) -> dict:
    """Generate an S3 event notification payload for Lambda invocation."""
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "ap-northeast-1",
                "eventTime": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z"
                ),
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                },
            }
        ]
    }


def main() -> int:
    """Generate test data files."""
    parser = argparse.ArgumentParser(
        description="Generate test audit log data with current timestamps"
    )
    parser.add_argument(
        "--output",
        default="/tmp/current_audit_logs.json",
        help="Output path for audit log file",
    )
    parser.add_argument(
        "--s3-event-output",
        default="/tmp/test_s3_event.json",
        help="Output path for S3 event JSON",
    )
    parser.add_argument(
        "--bucket",
        default="fsxn-audit-logs-observability-test",
        help="S3 bucket name for the event",
    )
    parser.add_argument(
        "--key",
        default="audit/svm-prod-01/current/audit_current.json",
        help="S3 object key",
    )
    args = parser.parse_args()

    # Generate audit logs
    audit_logs = generate_audit_logs()
    with open(args.output, "w") as f:
        f.write(audit_logs)
    print(f"Generated audit logs: {args.output} ({len(SAMPLE_EVENTS)} events)")

    # Generate S3 event
    s3_event = generate_s3_event(args.bucket, args.key)
    with open(args.s3_event_output, "w") as f:
        json.dump(s3_event, f, indent=2)
    print(f"Generated S3 event: {args.s3_event_output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
