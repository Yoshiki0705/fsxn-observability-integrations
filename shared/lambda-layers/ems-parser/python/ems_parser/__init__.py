"""EMS Parser Lambda Layer.

Provides utilities for parsing and normalizing ONTAP EMS (Event Management System)
Webhook payloads into a standardized format for downstream processing.
"""

__version__ = "0.1.0"

from .parser import EmsParseError, format_ems_event, parse_ems_event

__all__ = ["parse_ems_event", "format_ems_event", "EmsParseError"]
