"""EMS event type definitions and parameter schemas.

Defines the expected parameter schemas for known ONTAP EMS event types.
Used by the parser to validate and extract event-specific parameters.
"""

from __future__ import annotations

from typing import Any

# Parameter type definitions for schema validation.
# Each entry maps a parameter name to its expected Python type.
# Types: str, int, float
ParamSchema = dict[str, type]

# Valid states for ARP volume events
ARP_VOLUME_STATES = frozenset({"enabled", "disabled", "dry-run", "paused"})

# Severity levels used by ONTAP EMS
SEVERITY_LEVELS = frozenset({
    "emergency",
    "alert",
    "error",
    "warning",
    "notice",
    "informational",
    "debug",
})

# Event type definitions mapping event names to their expected parameter schemas.
# Each schema defines the parameter field names and their expected types.
# Unknown event types are handled gracefully (parameters passed through as-is).
EVENT_TYPE_SCHEMAS: dict[str, ParamSchema] = {
    "arw.volume.state": {
        "volume_name": str,
        "state": str,
    },
    "arw.vserver.state": {
        "vserver_name": str,
        "state": str,
    },
    "wafl.quota.softlimit.exceeded": {
        "volume_name": str,
        "qtree": str,
        "quota_target": str,
        "used_bytes": int,
        "limit_bytes": int,
    },
    "wafl.quota.hardlimit.exceeded": {
        "volume_name": str,
        "qtree": str,
        "quota_target": str,
        "used_bytes": int,
        "limit_bytes": int,
    },
    "sms.vol.full": {
        "volume_name": str,
        "used_percent": int,
    },
    "cf.fsm.takeoverStarted": {
        "partner_node": str,
        "reason": str,
    },
    "net.linkDown": {
        "node": str,
        "port": str,
        "reason": str,
    },
}

# Default severity for known event types (used for validation/reference)
EVENT_DEFAULT_SEVERITY: dict[str, str] = {
    "arw.volume.state": "alert",
    "arw.vserver.state": "alert",
    "wafl.quota.softlimit.exceeded": "warning",
    "wafl.quota.hardlimit.exceeded": "error",
    "sms.vol.full": "error",
    "cf.fsm.takeoverStarted": "alert",
    "net.linkDown": "alert",
}


def get_event_schema(event_name: str) -> ParamSchema | None:
    """Get the parameter schema for a known event type.

    Args:
        event_name: The EMS event name (e.g., "arw.volume.state").

    Returns:
        Parameter schema dict if event type is known, None otherwise.
    """
    return EVENT_TYPE_SCHEMAS.get(event_name)


def is_known_event_type(event_name: str) -> bool:
    """Check if an event type is in the known event registry.

    Args:
        event_name: The EMS event name to check.

    Returns:
        True if the event type is known, False otherwise.
    """
    return event_name in EVENT_TYPE_SCHEMAS


def get_known_event_names() -> list[str]:
    """Get a list of all known event type names.

    Returns:
        List of known EMS event names.
    """
    return list(EVENT_TYPE_SCHEMAS.keys())


def validate_parameters(event_name: str, parameters: dict[str, Any]) -> bool:
    """Validate that parameters match the expected schema for a known event type.

    Args:
        event_name: The EMS event name.
        parameters: The parameters dict to validate.

    Returns:
        True if parameters are valid or event type is unknown.
        False if a known event type has missing required parameters.
    """
    schema = get_event_schema(event_name)
    if schema is None:
        # Unknown event types always pass validation
        return True

    for field_name in schema:
        if field_name not in parameters:
            return False

    return True
