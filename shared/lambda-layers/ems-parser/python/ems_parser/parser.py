"""EMS event parser core logic.

Parses ONTAP EMS Webhook JSON payloads into normalized dictionaries
for downstream processing by vendor integrations.
"""

from __future__ import annotations

import json
from typing import Any

from .event_types import get_event_schema, is_known_event_type

# Maximum allowed length for the message field.
_MAX_MESSAGE_LENGTH = 2048


class EmsParseError(Exception):
    """Raised when an EMS event payload cannot be parsed.

    Attributes:
        message: Human-readable error description including the reason
            for parse failure (e.g., missing field name, JSON syntax error).
    """

    pass


def parse_ems_event(payload: str | dict) -> dict[str, Any]:
    """Parse an EMS event payload into a normalized dictionary.

    Accepts either a JSON string or a dict as input. Validates that
    required fields are present and maps input fields to the normalized
    output format.

    Args:
        payload: Raw EMS event as JSON string or dict.

    Returns:
        Normalized dictionary with fields:
        - timestamp: ISO 8601 string (from input ``time``)
        - event_name: str (from input ``messageName``)
        - severity: str (from input ``severity``)
        - source_node: str (from input ``node``)
        - svm: str (from input ``svmName``)
        - message: str (max 2048 chars, from input ``message``)
        - parameters: dict (event-type-specific, from input ``parameters``)
        - raw: dict (original payload)

    Raises:
        EmsParseError: If payload is invalid (bad JSON, None, empty,
                       or missing required fields).
    """
    # Validate None input
    if payload is None:
        raise EmsParseError("payload is None")

    # Validate empty string
    if isinstance(payload, str) and payload == "":
        raise EmsParseError("payload is empty")

    # Parse JSON string to dict
    if isinstance(payload, str):
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError as e:
            raise EmsParseError(f"invalid JSON: {e}") from e
    elif isinstance(payload, dict):
        data = payload
    else:
        raise EmsParseError(f"payload must be str or dict, got {type(payload).__name__}")

    # Detect if input is already a normalized dict (from format_ems_event round-trip).
    # A normalized dict has "event_name" and "raw" keys at the top level.
    if "event_name" in data and "raw" in data and isinstance(data["raw"], dict):
        # Re-parse from the embedded raw payload to ensure consistent output
        return parse_ems_event(data["raw"])

    # Validate required fields
    if "messageName" not in data:
        raise EmsParseError("missing required field: messageName")
    if "parameters" not in data:
        raise EmsParseError("missing required field: parameters")

    # Extract and map fields
    event_name: str = data["messageName"]
    raw_message: str = data.get("message", "")
    parameters: dict[str, Any] = data["parameters"]

    # Truncate message to max length
    message = raw_message[:_MAX_MESSAGE_LENGTH] if len(raw_message) > _MAX_MESSAGE_LENGTH else raw_message

    # For known event types, extract and validate parameters according to schema
    if is_known_event_type(event_name):
        schema = get_event_schema(event_name)
        if schema is not None:
            validated_params: dict[str, Any] = {}
            for field_name, field_type in schema.items():
                if field_name in parameters:
                    value = parameters[field_name]
                    # Attempt type coercion for known fields
                    if field_type is int and not isinstance(value, int):
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            value = parameters[field_name]
                    validated_params[field_name] = value
                else:
                    # Field missing from input — include what we have
                    pass
            # Include any extra parameters not in schema
            for key, value in parameters.items():
                if key not in validated_params:
                    validated_params[key] = value
            parameters = validated_params

    # Build normalized output
    normalized: dict[str, Any] = {
        "timestamp": data.get("time", ""),
        "event_name": event_name,
        "severity": data.get("severity", ""),
        "source_node": data.get("node", ""),
        "svm": data.get("svmName", ""),
        "message": message,
        "parameters": parameters,
        "raw": data,
    }

    return normalized


def format_ems_event(normalized: dict[str, Any]) -> str:
    """Serialize a normalized EMS event dict to JSON string.

    The output is suitable for storage or transmission and supports
    round-trip parsing: ``parse_ems_event(format_ems_event(parse_ems_event(payload)))``
    produces a dict equal to ``parse_ems_event(payload)``.

    Args:
        normalized: Dictionary from parse_ems_event().

    Returns:
        JSON string representation.
    """
    return json.dumps(normalized, ensure_ascii=False, default=str)
