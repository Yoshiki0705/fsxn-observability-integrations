"""Minimal hand-rolled OTLP/Protobuf encoder for the OTLP Logs Data Model.

Why this exists: some vendors' OTLP/HTTP log ingestion endpoints only accept
Protobuf-encoded request bodies and reject OTLP/JSON outright (confirmed for
Mackerel's log-feature endpoint, which returns HTTP 400
'{"code":400,"message":"json is not supported yet"}' for a JSON body). The
direct-send Lambda path (no OTel Collector in between) previously always sent
OTLP/JSON, so it could never reach those vendors even with correct auth.

Rather than adding the `protobuf`/`opentelemetry-proto` PyPI packages as a
Lambda dependency (this project intentionally keeps the Lambda runtime
dependency-free — only boto3/urllib3, both included in the Lambda Python
runtime), this module implements just the small subset of the Protobuf wire
format needed to encode an OTLP LogsData message: varint/length-delimited
field encoding, no external dependencies, no code generation step.

Field numbers below are taken verbatim from the official OTLP proto
definitions (Apache License 2.0):
- https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/logs/v1/logs.proto
- https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/common/v1/common.proto
- https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/resource/v1/resource.proto

This module only encodes the fields already used by this repo's OTLP/JSON
payload builders (service.name/cloud.* resource attributes, one
InstrumentationScope name+version, and LogRecord time_unix_nano/
severity_number/severity_text/body(string)/attributes(string-valued)). It
does not attempt to be a general-purpose OTLP Protobuf library.
"""

from __future__ import annotations

from typing import Any


# ─── Low-level Protobuf wire-format primitives ─────────────────────────────


def _varint(value: int) -> bytes:
    """Encode an unsigned integer as a Protobuf varint."""
    if value < 0:
        raise ValueError("varint encoding requires a non-negative integer")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _tag(field_number: int, wire_type: int) -> bytes:
    """Encode a Protobuf field tag (field_number << 3 | wire_type)."""
    return _varint((field_number << 3) | wire_type)


def _len_delimited(field_number: int, payload: bytes) -> bytes:
    """Encode a length-delimited field (wire type 2): messages, strings, bytes."""
    return _tag(field_number, 2) + _varint(len(payload)) + payload


def _string_field(field_number: int, value: str) -> bytes:
    """Encode a string field (wire type 2)."""
    return _len_delimited(field_number, value.encode("utf-8"))


def _varint_field(field_number: int, value: int) -> bytes:
    """Encode a varint field (wire type 0): used for enums like severity_number."""
    return _tag(field_number, 0) + _varint(value)


def _fixed64_field(field_number: int, value: int) -> bytes:
    """Encode a fixed64 field (wire type 1): used for time_unix_nano."""
    return _tag(field_number, 1) + int(value).to_bytes(8, byteorder="little", signed=False)


# ─── OTLP message encoders ─────────────────────────────────────────────────


def _encode_any_value_string(value: str) -> bytes:
    """Encode an AnyValue message containing only string_value (field 1)."""
    return _string_field(1, value)


def _encode_key_value(key: str, value: str) -> bytes:
    """Encode a KeyValue message: key (field 1, string), value (field 2, AnyValue)."""
    body = _string_field(1, key)
    body += _len_delimited(2, _encode_any_value_string(value))
    return body


def _encode_instrumentation_scope(name: str, version: str = "") -> bytes:
    """Encode an InstrumentationScope message: name (field 1), version (field 2)."""
    body = _string_field(1, name)
    if version:
        body += _string_field(2, version)
    return body


def _encode_resource(attributes: list[dict[str, Any]]) -> bytes:
    """Encode a Resource message: repeated KeyValue attributes (field 1).

    Args:
        attributes: List of OTLP-JSON-style attribute dicts, e.g.
            [{"key": "service.name", "value": {"stringValue": "fsxn-audit"}}].
            Only stringValue attributes are supported (sufficient for this
            repo's resource attributes: service.name, cloud.provider, etc.).
    """
    body = b""
    for attr in attributes:
        key = attr["key"]
        value = attr.get("value", {}).get("stringValue", "")
        body += _len_delimited(1, _encode_key_value(key, value))
    return body


def _encode_log_record(log_record: dict[str, Any]) -> bytes:
    """Encode a LogRecord message from its OTLP-JSON-style dict representation.

    Supported fields: timeUnixNano (field 1, fixed64), severityNumber (field 2,
    varint), severityText (field 3, string), body.stringValue (field 5,
    AnyValue), attributes (field 6, repeated KeyValue, stringValue only).
    """
    body = b""

    time_unix_nano = log_record.get("timeUnixNano")
    if time_unix_nano is not None:
        body += _fixed64_field(1, int(time_unix_nano))

    severity_number = log_record.get("severityNumber")
    if severity_number is not None:
        body += _varint_field(2, int(severity_number))

    severity_text = log_record.get("severityText")
    if severity_text:
        body += _string_field(3, severity_text)

    log_body = log_record.get("body", {}).get("stringValue")
    if log_body is not None:
        body += _len_delimited(5, _encode_any_value_string(log_body))

    for attr in log_record.get("attributes", []):
        key = attr["key"]
        value = attr.get("value", {}).get("stringValue", "")
        body += _len_delimited(6, _encode_key_value(key, value))

    return body


def _encode_scope_logs(scope_logs: dict[str, Any]) -> bytes:
    """Encode a ScopeLogs message: scope (field 1), log_records (field 2, repeated)."""
    body = b""

    scope = scope_logs.get("scope")
    if scope:
        body += _len_delimited(
            1, _encode_instrumentation_scope(scope.get("name", ""), scope.get("version", ""))
        )

    for log_record in scope_logs.get("logRecords", []):
        body += _len_delimited(2, _encode_log_record(log_record))

    return body


def _encode_resource_logs(resource_logs: dict[str, Any]) -> bytes:
    """Encode a ResourceLogs message: resource (field 1), scope_logs (field 2, repeated)."""
    body = b""

    resource = resource_logs.get("resource")
    if resource:
        body += _len_delimited(1, _encode_resource(resource.get("attributes", [])))

    for scope_logs in resource_logs.get("scopeLogs", []):
        body += _len_delimited(2, _encode_scope_logs(scope_logs))

    return body


def encode_logs_data(otlp_json_payload: dict[str, Any]) -> bytes:
    """Encode an OTLP-JSON-style logs payload as OTLP/Protobuf (LogsData message).

    This takes the same dict structure this repo's *_otlp_payload builder
    functions already produce (resourceLogs -> scopeLogs -> logRecords) and
    serializes it to the equivalent Protobuf wire format, so no separate
    payload-building code path is needed for vendors that require Protobuf.

    Args:
        otlp_json_payload: Dict with a top-level "resourceLogs" list, in the
            same shape as build_otlp_payload()/build_ems_otlp_payload()/
            build_fpolicy_otlp_payload() already produce.

    Returns:
        Serialized bytes for the OTLP LogsData Protobuf message
        (top-level field: repeated ResourceLogs resource_logs = 1).
    """
    body = b""
    for resource_logs in otlp_json_payload.get("resourceLogs", []):
        body += _len_delimited(1, _encode_resource_logs(resource_logs))
    return body
