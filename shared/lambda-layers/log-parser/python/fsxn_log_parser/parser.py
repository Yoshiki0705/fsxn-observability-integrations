"""FSx ONTAP audit log parser.

Supports EVTX (Windows Event Log) and JSON log formats.
"""

import json
import struct
from datetime import datetime, timezone
from typing import Any


def parse_evtx(data: bytes) -> list[dict[str, Any]]:
    """Parse EVTX format audit log data.

    Args:
        data: Raw EVTX binary data.

    Returns:
        List of normalized event dictionaries.
    """
    events = []
    # EVTX magic: "ElfFile\x00"
    if not data.startswith(b"ElfFile\x00"):
        raise ValueError("Invalid EVTX file: missing magic header")

    # Simplified EVTX parsing - production implementation would use
    # a full EVTX parser library
    # For now, extract basic record structure
    offset = 4096  # Skip file header (4KB)
    while offset < len(data):
        try:
            # Check for record magic "**\x00\x00"
            if data[offset : offset + 4] == b"\x2a\x2a\x00\x00":
                record_size = struct.unpack_from("<I", data, offset + 4)[0]
                record_data = data[offset : offset + record_size]
                event = _parse_evtx_record(record_data)
                if event:
                    events.append(normalize_event(event))
                offset += record_size
            else:
                offset += 1
        except (struct.error, IndexError):
            break

    return events


def parse_json_log(data: str) -> list[dict[str, Any]]:
    """Parse JSON format audit log data.

    Args:
        data: JSON string (single object or newline-delimited).

    Returns:
        List of normalized event dictionaries.
    """
    events = []
    for line in data.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            events.append(normalize_event(event))
        except json.JSONDecodeError:
            continue
    return events


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize an audit event to a common schema.

    Args:
        event: Raw event dictionary.

    Returns:
        Normalized event with standard fields.
    """
    return {
        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "event_type": event.get("EventID", event.get("event_type", "unknown")),
        "source": "fsxn-ontap",
        "svm": event.get("SVMName", event.get("svm", "")),
        "user": event.get("UserName", event.get("user", "")),
        "client_ip": event.get("ClientIP", event.get("client_ip", "")),
        "operation": event.get("Operation", event.get("operation", "")),
        "path": event.get("ObjectName", event.get("path", "")),
        "result": event.get("Result", event.get("result", "")),
        "raw": event,
    }


def _parse_evtx_record(record_data: bytes) -> dict[str, Any] | None:
    """Parse a single EVTX record.

    Args:
        record_data: Raw record bytes.

    Returns:
        Parsed event dictionary or None if parsing fails.
    """
    try:
        # Extract basic fields from record header
        record_num = struct.unpack_from("<Q", record_data, 8)[0]
        timestamp_raw = struct.unpack_from("<Q", record_data, 16)[0]

        # Convert Windows FILETIME to ISO timestamp
        # FILETIME: 100-nanosecond intervals since 1601-01-01
        if timestamp_raw > 0:
            epoch_diff = 116444736000000000  # diff between 1601 and 1970 in 100ns
            timestamp_seconds = (timestamp_raw - epoch_diff) / 10_000_000
            timestamp = datetime.fromtimestamp(
                timestamp_seconds, tz=timezone.utc
            ).isoformat()
        else:
            timestamp = datetime.now(timezone.utc).isoformat()

        return {
            "record_number": record_num,
            "timestamp": timestamp,
            "EventID": "unknown",
        }
    except (struct.error, ValueError, OSError):
        return None
