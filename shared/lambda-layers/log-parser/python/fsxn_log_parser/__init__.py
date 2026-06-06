"""FSx ONTAP Log Parser Lambda Layer.

Provides utilities for parsing FSx for NetApp ONTAP audit logs
in EVTX, XML, and JSON formats.
"""

__version__ = "1.0.0"

from .parser import (
    AuditEvent,
    MetricsCallback,
    ParseResult,
    detect_format,
    normalize_event,
    parse,
    parse_evtx,
    parse_json_log,
    parse_xml_log,
    register_format,
    validate_event,
)
