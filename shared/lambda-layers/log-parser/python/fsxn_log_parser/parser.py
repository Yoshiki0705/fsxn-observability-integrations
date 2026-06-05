"""FSx ONTAP audit log parser.

Supports EVTX (Windows Event Log) and XML log formats.
ONTAP audit logs are created via `vserver audit create -format {evtx|xml}`.
"""

import json
import struct
import xml.etree.ElementTree as ET
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
    """Parse JSON format audit log data (fallback for non-standard formats).

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


def parse_xml_log(data: str) -> list[dict[str, Any]]:
    """Parse XML format audit log data.

    ONTAP generates XML audit logs when configured with `-format xml`.
    The XML contains Event elements with system and event data.

    Args:
        data: XML string content.

    Returns:
        List of normalized event dictionaries.
    """
    events = []

    try:
        # Handle multiple root elements by wrapping
        if not data.strip().startswith("<?xml"):
            data = f"<AuditEvents>{data}</AuditEvents>"
        else:
            lines = data.strip().split("\n")
            if lines[0].startswith("<?xml"):
                data = f"<AuditEvents>{''.join(lines[1:])}</AuditEvents>"

        root = ET.fromstring(data)

        for event_elem in root.iter("Event"):
            raw = _xml_element_to_flat_dict(event_elem)
            events.append(normalize_event(raw))

        if not events:
            for child in root:
                raw = _xml_element_to_flat_dict(child)
                if raw:
                    events.append(normalize_event(raw))

    except ET.ParseError:
        pass

    return events


def _xml_element_to_flat_dict(elem) -> dict[str, Any]:
    """Convert an XML element tree to a flat dictionary.

    Handles ONTAP's <Data Name="key">value</Data> pattern correctly,
    collecting all Data elements instead of overwriting with the last one.
    """
    result: dict[str, Any] = {}
    for child in elem.iter():
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        # Handle <Data Name="key">value</Data> pattern (ONTAP EventData)
        if tag == "Data" and "Name" in child.attrib:
            key = child.attrib["Name"]
            if child.text and child.text.strip():
                result[key] = child.text.strip()
        elif child.text and child.text.strip():
            result[tag] = child.text.strip()

        # Capture attributes (e.g., TimeCreated SystemTime="...")
        for attr_name, attr_value in child.attrib.items():
            if attr_name != "Name":  # Skip the "Name" attr from Data elements
                result[f"{tag}_{attr_name}"] = attr_value
    return result


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize an audit event to a common schema.

    Maps both ONTAP EVTX/XML field names and generic field names.

    Args:
        event: Raw event dictionary.

    Returns:
        Normalized event with standard fields.
    """
    return {
        "timestamp": event.get("TimeCreated_SystemTime", event.get("timestamp",
                     datetime.now(timezone.utc).isoformat())),
        "event_type": event.get("EventID", event.get("event_type", "unknown")),
        "source": "fsxn-ontap",
        "svm": event.get("Computer", event.get("SVMName", event.get("svm", ""))),
        "user": event.get("SubjectUserName", event.get("UserName", event.get("user", ""))),
        "client_ip": event.get("IpAddress", event.get("ClientIP", event.get("client_ip", ""))),
        "operation": event.get("ObjectType", event.get("Operation", event.get("operation", ""))),
        "path": event.get("ObjectName", event.get("path", "")),
        "result": event.get("Keywords", event.get("Result", event.get("result", ""))),
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
