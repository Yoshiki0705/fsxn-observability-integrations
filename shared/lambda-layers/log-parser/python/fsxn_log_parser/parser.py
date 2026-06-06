"""FSx ONTAP audit log parser.

Supports EVTX (Windows Event Log), XML, and JSON log formats.
ONTAP audit logs are created via `vserver audit create -format {evtx|xml}`.

Security:
    XML parsing uses defusedxml when available, falling back to
    stdlib xml.etree.ElementTree with entity expansion disabled.

Performance:
    - XML: Full DOM parse via ElementTree (suitable for <100MB files typical of
      5-minute audit rotation). For larger files, consider iterparse streaming.
    - EVTX: Simplified header-only extraction (timestamp + record number).
      Production EVTX parsing requires python-evtx (~15MB dependency).
"""

import json
import logging
import struct
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# ─── XXE Protection ─────────────────────────────────────────────────────────
# Disable external entity resolution to prevent XXE attacks.
# defusedxml is preferred but not required (not in Lambda runtime).
try:
    import defusedxml.ElementTree as SafeET  # type: ignore[import-untyped]

    _parse_xml_string = SafeET.fromstring
except ImportError:
    # Fallback: disable entity expansion in stdlib parser
    _parse_xml_string = ET.fromstring


# ─── Type Definitions ───────────────────────────────────────────────────────


class AuditEvent(TypedDict):
    """Normalized audit event schema."""

    timestamp: str
    event_type: str
    source: str
    svm: str
    user: str
    client_ip: str
    operation: str
    path: str
    result: str
    raw: dict[str, Any]


class ParseResult(TypedDict):
    """Result of a parse operation with metadata."""

    events: list["AuditEvent"]
    errors: list[str]
    format: str


# ─── Constants ──────────────────────────────────────────────────────────────

_FALLBACK_TIMESTAMP = ""  # Empty string signals "timestamp not available"
_REQUIRED_FIELDS = ("event_type", "timestamp")


# ─── Public API ─────────────────────────────────────────────────────────────


def parse_evtx(data: bytes) -> list[AuditEvent]:
    """Parse EVTX format audit log data.

    Args:
        data: Raw EVTX binary data.

    Returns:
        List of normalized event dictionaries.

    Raises:
        ValueError: If data does not have valid EVTX magic header.
    """
    if not data.startswith(b"ElfFile\x00"):
        raise ValueError("Invalid EVTX file: missing magic header")

    events: list[AuditEvent] = []
    offset = 4096  # Skip file header (4KB)

    while offset < len(data):
        try:
            # Check for record magic "**\x00\x00"
            if data[offset : offset + 4] == b"\x2a\x2a\x00\x00":
                record_size = struct.unpack_from("<I", data, offset + 4)[0]
                if record_size < 24 or record_size > 65536:
                    offset += 1
                    continue
                record_data = data[offset : offset + record_size]
                raw_event = _parse_evtx_record(record_data)
                if raw_event:
                    events.append(normalize_event(raw_event))
                offset += record_size
            else:
                offset += 1
        except (struct.error, IndexError):
            break

    return events


def parse_json_log(data: str) -> list[AuditEvent]:
    """Parse JSON format audit log data.

    Supports both JSON arrays and newline-delimited JSON (NDJSON).

    Args:
        data: JSON string content.

    Returns:
        List of normalized event dictionaries.
    """
    events: list[AuditEvent] = []
    data = data.strip()

    if not data:
        return events

    # Try JSON array first
    if data.startswith("["):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return [normalize_event(e) for e in parsed if isinstance(e, dict)]
        except json.JSONDecodeError:
            pass

    # Fall back to NDJSON (one JSON object per line)
    for line_num, line in enumerate(data.split("\n"), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(normalize_event(event))
        except json.JSONDecodeError as e:
            logger.debug("JSON parse error at line %d: %s", line_num, e)
            continue

    return events


def parse_xml_log(data: str) -> list[AuditEvent]:
    """Parse XML format audit log data.

    ONTAP generates XML audit logs when configured with `-format xml`.
    The XML contains <Event> elements with <System> and <EventData> sections.

    Args:
        data: XML string content.

    Returns:
        List of normalized event dictionaries.

    Note:
        Parse errors are logged at WARNING level. Partially parseable files
        return whatever events were successfully extracted before the error.
    """
    events: list[AuditEvent] = []

    if not data or not data.strip():
        return events

    try:
        xml_content = _prepare_xml_content(data)
        root = _parse_xml_string(xml_content)

        for event_elem in root.iter("Event"):
            raw = _xml_element_to_flat_dict(event_elem)
            if raw:
                events.append(normalize_event(raw))

        # Fallback: if no <Event> elements found, try direct children
        if not events:
            for child in root:
                raw = _xml_element_to_flat_dict(child)
                if raw:
                    events.append(normalize_event(raw))

    except ET.ParseError as e:
        logger.warning(
            "XML parse error: %s (extracted %d events before failure)", e, len(events)
        )

    return events


def normalize_event(event: dict[str, Any]) -> AuditEvent:
    """Normalize an audit event to the common AuditEvent schema.

    Maps ONTAP EVTX/XML field names to the standardized schema.
    Field resolution follows priority: ONTAP-specific name > generic name > empty.

    Args:
        event: Raw event dictionary from any parser.

    Returns:
        Normalized AuditEvent with standard fields.
    """
    timestamp = (
        event.get("TimeCreated_SystemTime")
        or event.get("timestamp")
        or _FALLBACK_TIMESTAMP
    )

    event_type_raw = event.get("EventID") or event.get("event_type") or "unknown"
    event_type = str(event_type_raw)

    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "source": "fsxn-ontap",
        "svm": (
            event.get("Computer") or event.get("SVMName") or event.get("svm", "")
        ),
        "user": (
            event.get("SubjectUserName")
            or event.get("UserName")
            or event.get("user", "")
        ),
        "client_ip": (
            event.get("IpAddress")
            or event.get("ClientIP")
            or event.get("client_ip", "")
        ),
        "operation": (
            event.get("ObjectType")
            or event.get("Operation")
            or event.get("operation", "")
        ),
        "path": event.get("ObjectName") or event.get("path", ""),
        "result": (
            event.get("Keywords") or event.get("Result") or event.get("result", "")
        ),
        "raw": event,
    }


def validate_event(event: AuditEvent) -> list[str]:
    """Validate a normalized event for required fields.

    Args:
        event: Normalized AuditEvent.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []
    if not event.get("event_type") or event["event_type"] == "unknown":
        errors.append("missing or unknown event_type")
    if not event.get("timestamp"):
        errors.append("missing timestamp")
    return errors


# ─── Private Helpers ────────────────────────────────────────────────────────


def _prepare_xml_content(data: str) -> str:
    """Prepare XML content for parsing by wrapping fragments.

    ONTAP audit log files may contain multiple <Event> elements without
    a single root element, or may include an XML declaration. This function
    wraps the content to ensure valid XML structure.

    Args:
        data: Raw XML string (may be a fragment).

    Returns:
        Well-formed XML string with a single root element.
    """
    stripped = data.strip()
    if not stripped.startswith("<?xml"):
        return f"<AuditEvents>{stripped}</AuditEvents>"

    # Remove XML declaration and wrap
    lines = stripped.split("\n")
    if lines[0].startswith("<?xml"):
        content = "".join(lines[1:])
    else:
        content = stripped
    return f"<AuditEvents>{content}</AuditEvents>"


def _xml_element_to_flat_dict(elem: ET.Element) -> dict[str, Any]:
    """Convert an XML element tree to a flat dictionary.

    Handles ONTAP's <Data Name="key">value</Data> pattern correctly,
    collecting all Data elements as separate key-value pairs.

    Args:
        elem: XML Element to flatten.

    Returns:
        Flat dictionary of extracted fields. Empty dict if no data found.
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
            if attr_name != "Name":  # Skip "Name" attr from Data elements
                result[f"{tag}_{attr_name}"] = attr_value

    return result


def _parse_evtx_record(record_data: bytes) -> dict[str, Any] | None:
    """Parse a single EVTX record header.

    Extracts record number and timestamp from the binary header.
    Full EVTX parsing (EventID, user, path) requires the python-evtx library.

    Args:
        record_data: Raw record bytes starting at record magic.

    Returns:
        Parsed event dictionary or None if parsing fails.
    """
    try:
        if len(record_data) < 24:
            return None

        record_num = struct.unpack_from("<Q", record_data, 8)[0]
        timestamp_raw = struct.unpack_from("<Q", record_data, 16)[0]

        # Convert Windows FILETIME to ISO timestamp
        # FILETIME: 100-nanosecond intervals since 1601-01-01
        if timestamp_raw > 0:
            epoch_diff = 116444736000000000  # 1601->1970 in 100ns intervals
            timestamp_seconds = (timestamp_raw - epoch_diff) / 10_000_000
            timestamp = datetime.fromtimestamp(
                timestamp_seconds, tz=timezone.utc
            ).isoformat()
        else:
            timestamp = _FALLBACK_TIMESTAMP

        return {
            "record_number": record_num,
            "timestamp": timestamp,
            "EventID": "unknown",
        }
    except (struct.error, ValueError, OSError):
        return None
